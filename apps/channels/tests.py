"""Synthetic fixtures/mocks only. These tests are NOT marketplace certification."""
import hashlib
import hmac
import json
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase,Client,override_settings
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.stores.models import Category,Product
from apps.orders.models import Order,StockReservation,OrderStatusNotification,OrderStatusEvent
from apps.orders.operations import transition_order,allowed_transitions,OrderOperationError,_queue_notification
from apps.orders.inventory import cancel
from apps.billing.online import create_order_checkout,BillingError
from apps.billing.models import OrderPayment
from apps.billing.secrets import decrypt_secret
from .models import Connection,ExternalOrder,Inbox,Outbox,ProductLink,AppToken
from .services import receive,apply_event,process_event,process_command,presentation
from .connectors import IFood,BlockedConnector,ProviderError,valid_ifood_signature
from .normalize import normalize_ifood
from .simulator import sample,simulate
from .tasks import poll_ifood,drain

@override_settings(CHANNELS_SIMULATOR_ENABLED=True,CHANNELS_NETWORK_ENABLED=False,CHANNELS_LIVE_ENABLED=False)
class ChannelTests(TestCase):
    def setUp(self):
        self.a=Tenant.objects.create(name='Loja A',slug='loja-a',whatsapp_number='5511999991111')
        self.b=Tenant.objects.create(name='Loja B',slug='loja-b',whatsapp_number='5511999992222')
        self.user=get_user_model().objects.create_user(username='merchant-channel',password='Test-only-123!',tenant=self.a,is_staff=True,is_tenant_admin=True)
        self.client=Client(HTTP_HOST='loja-a.lvh.me');self.client.force_login(self.user)
        self.conn=Connection.objects.create(tenant=self.a,provider='ifood',mode='simulation',merchant_id='test-merchant',enabled=True,status='connected')
        self.cat=Category.objects.create(tenant=self.a,name='Lanches',slug='lanches')
        self.product=Product.objects.create(tenant=self.a,category=self.cat,name='Lanche',slug='lanche',price='10',stock=10)
        ProductLink.objects.create(connection=self.conn,external_code='DEMO-LANCHE',product=self.product)
        self.raw=json.loads((Path(__file__).parent/'fixtures/ifood_food.json').read_text())
        self.dto=normalize_ifood(self.raw)
        self.t=timezone.now()
        self.addCleanup(patch.stopall)
        patch('apps.orders.realtime.publish_order_event').start()
    def event(self,code='PLACED',key=None,offset=0,conn=None,dto=None):
        c=conn or self.conn;d=dto or self.dto
        e=receive(c,{'id':key or code,'orderId':d['external_id'],'merchantId':c.merchant_id,'code':code,'createdAt':(self.t+timedelta(seconds=offset)).isoformat()})
        apply_event(e.pk,normalized=d,raw=self.raw if c.provider=='ifood' else None)
        return ExternalOrder.objects.get(connection=c,external_id=d['external_id'])
    def test_ifood_receipt_preserves_amounts_additions_and_encrypts(self):
        x=self.event();o=x.order
        self.assertEqual(o.source,'ifood');self.assertEqual(o.total,Decimal('49.90'))
        self.assertEqual(o.items.get().notes,'Sem cebola');self.assertIn('Queijo',str(o.items.get().combination_details))
        self.assertEqual(o.customer_phone,'');self.assertIsNone(o.customer_id)
        self.assertNotIn('Cliente fictício',x.encrypted_snapshot)
        self.assertEqual(json.loads(decrypt_secret(x.encrypted_snapshot))['provider'],self.raw)
    def test_99food_internal_fixture_receipt(self):
        c=Connection.objects.create(tenant=self.a,provider='99food',mode='simulation',merchant_id='sim99',enabled=True)
        x=self.event(conn=c,dto=sample(c));self.assertEqual(x.order.source,'99food')
        self.assertEqual(presentation(x.order)['channel_label'],'99Food')
    def test_duplicate_event_and_order_are_idempotent(self):
        x=self.event();self.event();self.event(key='second-placement')
        self.assertEqual(Order.objects.count(),1);self.assertEqual(ExternalOrder.objects.count(),1)
        self.assertEqual(Inbox.objects.count(),2);self.assertEqual(x.order.items.count(),1)
    def test_same_event_id_different_order_rejected(self):
        self.event()
        with self.assertRaises(ProviderError):receive(self.conn,{'id':'PLACED','orderId':'other','merchantId':self.conn.merchant_id,'code':'PLC','createdAt':self.t.isoformat()})
    def test_out_of_order_and_regression(self):
        x=self.event('PREPARATION_STARTED',offset=10)
        self.event('PLACED',offset=0);self.event('CONFIRMED',offset=20)
        x.order.refresh_from_db();self.assertEqual(x.order.status,'preparing')
        self.assertEqual(Inbox.objects.filter(state='ignored').count(),2)
    def test_stock_once_and_return_once(self):
        x=self.event();self.product.refresh_from_db();self.assertEqual(self.product.stock,10)
        self.event('CONFIRMED',offset=1);self.event('PREPARATION_STARTED',offset=2)
        self.product.refresh_from_db();self.assertEqual(self.product.stock,9)
        self.event('CANCELLED',offset=3);self.event('CANCELLED',key='cancel-repeat',offset=4)
        self.product.refresh_from_db();self.assertEqual(self.product.stock,10)
        self.assertEqual(StockReservation.objects.filter(order=x.order).count(),1)
    def test_insufficient_stock_keeps_external_order(self):
        self.product.stock=0;self.product.save()
        x=self.event('CONFIRMED');self.assertEqual(x.stock_state,'error');self.assertEqual(x.order.status,'confirmed')
    def test_unmapped_product_warns_without_decrement(self):
        ProductLink.objects.all().delete();x=self.event('CONFIRMED')
        self.product.refresh_from_db();self.assertEqual(self.product.stock,10);self.assertEqual(x.stock_state,'partial')
    def test_cross_tenant_product_mapping_rejected(self):
        c=Connection.objects.create(tenant=self.b,provider='ifood',mode='simulation',merchant_id='other',enabled=True)
        with self.assertRaises(ValidationError):ProductLink.objects.create(connection=c,external_code='P',product=self.product)
    def test_connection_cannot_be_owned_by_two_tenants(self):
        with self.assertRaises(IntegrityError),transaction.atomic():Connection.objects.create(tenant=self.b,provider='ifood',mode='simulation',merchant_id=self.conn.merchant_id)
    def test_wrong_merchant_rejected(self):
        with self.assertRaises(ProviderError):receive(self.conn,{'id':'x','orderId':'x','merchantId':'wrong','code':'PLC','createdAt':self.t.isoformat()})
        d=deepcopy(self.dto);d['merchant_id']='wrong'
        with self.assertRaises(ProviderError):self.event(dto=d)
        self.assertFalse(Order.objects.exists())
    def test_marketplace_never_creates_asaas_charge(self):
        o=self.event().order
        with self.assertRaises(BillingError):create_order_checkout(o,None)
        o.payment_flow='online';o.payment_method='PIX'
        with self.assertRaises(BillingError):create_order_checkout(o,None)
        self.assertFalse(OrderPayment.objects.exists())
    def test_payment_due_is_distinct(self):
        d=deepcopy(self.dto);d['paid']=False
        o=self.event(dto=d).order
        self.assertEqual(o.payment_flow,'marketplace_due')
    def test_external_never_queues_whatsapp_even_with_phone(self):
        o=self.event().order;o.customer_phone='5511999993333';o.save()
        e=OrderStatusEvent.objects.create(order=o,tenant=self.a,from_status='pending',to_status='confirmed')
        self.assertIsNone(_queue_notification(e));self.assertFalse(OrderStatusNotification.objects.exists())
    def test_command_is_persisted_before_status_change_and_simulated_after(self):
        o=self.event().order
        transition_order(order_id=o.pk,tenant=self.a,target_status='confirmed',actor=self.user)
        o.refresh_from_db();self.assertEqual(o.status,'pending')
        self.assertEqual(allowed_transitions(o),[])
        cmd=Outbox.objects.get();process_command(cmd.pk)
        o.refresh_from_db();cmd.refresh_from_db();self.assertEqual(o.status,'confirmed');self.assertEqual(cmd.state,'confirmed')
    def test_invalid_transition_and_foreign_tenant(self):
        o=self.event().order
        with self.assertRaises(OrderOperationError):transition_order(order_id=o.pk,tenant=self.a,target_status='delivered')
        with self.assertRaises(Order.DoesNotExist):transition_order(order_id=o.pk,tenant=self.b,target_status='confirmed')
        with self.assertRaises(ValueError):cancel(o.pk,self.a)
    def test_cancellation_requires_reason_and_confirmation(self):
        o=self.event().order
        with self.assertRaises(OrderOperationError):transition_order(order_id=o.pk,tenant=self.a,target_status='cancelled')
        transition_order(order_id=o.pk,tenant=self.a,target_status='cancelled',cancellation_code='SIM',cancellation_reason='Teste local')
        process_command(Outbox.objects.get().pk);o.refresh_from_db();self.assertEqual(o.status,'cancelled')
    def test_platform_delivery_and_pickup_cannot_dispatch(self):
        d=deepcopy(self.dto);d['delivery_by']='IFOOD';o=self.event('READY_TO_PICKUP',dto=d).order
        self.assertNotIn('out_for_delivery',allowed_transitions(o))
        d['external_id']='pickup';d['delivery_type']='pickup';o=self.event('READY_TO_PICKUP',key='pickup',dto=d).order
        self.assertEqual(o.status,'ready_for_pickup');self.assertNotIn('out_for_delivery',allowed_transitions(o))
    def test_scheduled_dispatch_waits_until_schedule(self):
        d=deepcopy(self.dto);d['scheduled_for']=(timezone.now()+timedelta(hours=1)).isoformat()
        o=self.event('READY_TO_PICKUP',dto=d).order
        self.assertNotIn('out_for_delivery',allowed_transitions(o))
    def test_terminal_conflict_never_resurrects(self):
        x=self.event('CANCELLED');self.event('CONCLUDED',offset=1)
        x.order.refresh_from_db();self.assertEqual(x.order.status,'cancelled')
    def test_api_board_kitchen_and_cross_tenant_isolation(self):
        x=self.event();self.event('CONFIRMED',offset=1)
        other=Connection.objects.create(tenant=self.b,provider='99food',mode='simulation',merchant_id='foreign',enabled=True)
        self.event(conn=other,dto=sample(other))
        for endpoint in ['orders','kitchen']:
            response=self.client.get('/api/merchant/'+endpoint+'/');self.assertEqual(response.status_code,200,response.content)
            data=response.json();rows=data['orders'] if endpoint=='kitchen' else [o for c in data['columns'] for o in c['orders']]
            self.assertEqual([o['id'] for o in rows],[x.order_id]);self.assertEqual(rows[0]['channel'],'ifood');self.assertEqual(rows[0]['external_id'],x.external_id)
    def test_kds_includes_only_external_pending(self):
        x=self.event();Order.objects.create(tenant=self.a,total=1,source='manual')
        data=self.client.get('/api/merchant/kitchen/').json();self.assertEqual([o['id'] for o in data['orders']],[x.order_id])
        self.assertIn('confirmed',[a['value'] for a in data['orders'][0]['allowed_transitions']])
    def test_kitchen_action_uses_async_transition(self):
        x=self.event();response=self.client.post(f'/api/merchant/kitchen/{x.order_id}/',{'status':'confirmed'},content_type='application/json')
        self.assertEqual(response.status_code,200,response.content);x.order.refresh_from_db();self.assertEqual(x.order.status,'pending');self.assertTrue(Outbox.objects.exists())
    def test_connection_settings_do_not_expose_credentials_and_disconnect_keeps_history(self):
        self.event();data=self.client.get('/api/merchant/integrations/').json()
        self.assertNotIn('secret',json.dumps(data));self.assertNotIn('encrypted',json.dumps(data))
        response=self.client.post('/api/merchant/integrations/',{'provider':'ifood','action':'disconnect','id':self.conn.pk},content_type='application/json')
        self.assertEqual(response.status_code,200);self.assertEqual(ExternalOrder.objects.count(),1)
        self.conn.refresh_from_db();self.assertFalse(self.conn.enabled);self.assertEqual(allowed_transitions(ExternalOrder.objects.get().order),[])
    def test_events_paginated_and_tenant_scoped(self):
        for n in range(12):self.event(key=str(n))
        data=self.client.get('/api/merchant/integrations/events/').json();self.assertEqual(len(data['events']),10);self.assertEqual(data['pagination']['count'],12)
        data=self.client.get('/api/merchant/integrations/events/?page=2').json();self.assertEqual(len(data['events']),2)
    def test_foreign_connection_cannot_disconnect_or_cancel(self):
        c=Connection.objects.create(tenant=self.b,provider='99food',mode='simulation',merchant_id='foreign',enabled=True)
        x=self.event(conn=c,dto=sample(c))
        response=self.client.post('/api/merchant/integrations/',{'provider':'99food','action':'disconnect','id':c.pk},content_type='application/json');self.assertEqual(response.status_code,404)
        self.assertEqual(self.client.get(f'/api/merchant/orders/{x.order_id}/cancellation-reasons/').status_code,404)
    def test_own_sources_unchanged_and_primary_identity_green(self):
        for source in ['web','whatsapp','manual']:
            o=Order.objects.create(tenant=self.a,total=1,source=source,whatsapp_opened_at=timezone.now())
            self.assertEqual(presentation(o)['channel'],'vemdedelivery')
            transition_order(order_id=o.pk,tenant=self.a,target_status='confirmed');o.refresh_from_db()
            self.assertEqual(o.source,source);self.assertEqual(o.status,'confirmed')
        self.assertFalse(Outbox.objects.exists())
    def test_fractional_food_quantity_is_quarantined(self):
        self.raw['items'][0]['quantity']=1.5
        with self.assertRaises(ProviderError):normalize_ifood(self.raw)
    def test_line_total_preserved_despite_unit_rounding(self):
        self.raw['items'][0]['quantity']=3;self.raw['items'][0]['totalPrice']=10
        x=self.event(dto=normalize_ifood(self.raw));self.assertEqual(x.order.items.get().get_total_price(),Decimal('10'))
    def test_real_99food_calls_fail_closed(self):
        for method,args in [('detail',('x',)),('command',(None,'confirmed',{})),('poll',()),('merchants',())]:
            with self.assertRaises(ProviderError):getattr(BlockedConnector(),method)(*args)
    def test_simulator_requires_opt_in_and_is_idempotent(self):
        with override_settings(CHANNELS_SIMULATOR_ENABLED=False):
            with self.assertRaises(CommandError):simulate(self.a,'99food')
        x=simulate(self.a,'99food');y=simulate(self.a,'99food');self.assertEqual(x.pk,y.pk)
    def test_inbox_api_outage_backoff_survives_worker_runs(self):
        e=receive(self.conn,{'id':'fail','orderId':'new','merchantId':self.conn.merchant_id,'code':'PLC','createdAt':self.t.isoformat()})
        with patch('apps.channels.services.connector') as factory:
            factory.return_value.detail.side_effect=ProviderError('Indisponível',retryable=True)
            process_event(e.pk)
        e.refresh_from_db();self.assertEqual(e.state,'error');self.assertEqual(e.attempts,1);self.assertGreater(e.next_attempt,timezone.now())
        drain();e.refresh_from_db();self.assertEqual(e.attempts,1)
    def test_uncertain_command_never_blindly_resent(self):
        x=self.event();self.conn.mode='test';self.conn.save()
        transition_order(order_id=x.order_id,tenant=self.a,target_status='confirmed')
        with patch('apps.channels.services.connector') as factory:
            factory.return_value.command.side_effect=ProviderError('Timeout',uncertain=True)
            cmd=Outbox.objects.get();process_command(cmd.pk);process_command(cmd.pk)
            self.assertEqual(factory.return_value.command.call_count,1)
        cmd.refresh_from_db();self.assertEqual(cmd.state,'uncertain')
        self.event('CONFIRMED',offset=1);cmd.refresh_from_db();self.assertEqual(cmd.state,'confirmed')
    @override_settings(CHANNELS_NETWORK_ENABLED=True)
    def test_poll_persists_before_ack_and_uses_authorized_merchants(self):
        self.conn.mode='test';self.conn.save()
        event={'id':'polled','orderId':self.dto['external_id'],'merchantId':self.conn.merchant_id,'code':'PLC','createdAt':self.t.isoformat()}
        with patch('apps.channels.tasks.IFood') as factory:
            factory.return_value.poll.return_value=[event,{**event,'id':'foreign','merchantId':'not-bound'}]
            factory.return_value.acknowledge.side_effect=lambda ids:self.assertTrue(Inbox.objects.filter(external_id=ids[0]).exists())
            poll_ifood('test')
            factory.return_value.poll.assert_called_once_with(['test-merchant']);factory.return_value.acknowledge.assert_called_once_with(['polled'])
        self.assertEqual(Inbox.objects.count(),1)
    @override_settings(CHANNELS_NETWORK_ENABLED=True,IFOOD_TEST_CLIENT_SECRET='test-secret')
    def test_webhook_signature_raw_body_and_replay(self):
        self.conn.mode='test';self.conn.save()
        body=json.dumps({'id':'webhook','orderId':self.dto['external_id'],'merchantId':self.conn.merchant_id,'code':'PLC','createdAt':self.t.isoformat()}).encode()
        signature=hmac.new(b'test-secret',body,hashlib.sha256).hexdigest()
        self.assertTrue(valid_ifood_signature(body,signature,'test'));self.assertFalse(valid_ifood_signature(body+b' ',signature,'test'))
        url='/integracoes/ifood/test/webhook/'
        self.assertEqual(self.client.post(url,body,content_type='application/json').status_code,401)
        for _ in range(2):self.assertEqual(self.client.post(url,body,content_type='application/json',HTTP_X_IFOOD_SIGNATURE=signature).status_code,202)
        self.assertEqual(Inbox.objects.count(),1)
    def test_no_network_without_explicit_enable(self):
        with patch('requests.request') as request:
            with self.assertRaises(ProviderError):IFood().token()
            request.assert_not_called()
    @override_settings(CHANNELS_NETWORK_ENABLED=True,IFOOD_TEST_CLIENT_ID='fake-id',IFOOD_TEST_CLIENT_SECRET='fake-secret')
    def test_expired_token_renews_and_cache_encrypted(self):
        api=IFood()
        with patch.object(api,'_http',return_value={'accessToken':'fake-access-token','expiresIn':60}) as http:
            api.token();api.token();self.assertEqual(http.call_count,1)
            row=AppToken.objects.get();self.assertNotIn('fake-access-token',row.encrypted_token)
            row.expires_at=timezone.now()-timedelta(seconds=1);row.save();api.token();self.assertEqual(http.call_count,2)
    def test_unauthorized_response_renews_once(self):
        api=IFood()
        with patch.object(api,'token',side_effect=['old','new']) as token,patch.object(api,'_http',side_effect=[ProviderError('iFood: autorização expirada ou inválida.'),[]]):
            self.assertEqual(api.poll(['test-merchant']),[]);token.assert_called_with(force=True)
    def test_transport_timeout_and_server_error_do_not_expose_body(self):
        api=IFood()
        with patch('requests.request',side_effect=requests.Timeout('secret')):
            with self.assertRaises(ProviderError) as error:api._http('POST','/x')
            self.assertTrue(error.exception.uncertain);self.assertNotIn('secret',str(error.exception))
        with patch('requests.request',return_value=Mock(status_code=503)):
            with self.assertRaises(ProviderError) as error:api._http('GET','/x')
            self.assertTrue(error.exception.retryable)
    def test_ifood_cancellation_reasons_support_all_known_code_fields(self):
        api = IFood()
        with patch.object(api, 'request', return_value={'reasons': [
            {'cancelCodeId': '501', 'description': 'Problemas de sistema'},
            {'code': '502', 'description': 'Pedido duplicado'},
            {'cancelCode': '503', 'description': 'Item indisponível'},
        ]}):
            self.assertEqual([r['code'] for r in api.reasons('order-1')], ['501', '502', '503'])

    def test_ifood_cancellation_reasons_reject_missing_code(self):
        api = IFood()
        with patch.object(api, 'request', return_value={'reasons': [
            {'description': 'Motivo sem código'},
        ]}):
            with self.assertRaisesRegex(ProviderError, 'sem código válido'):
                api.reasons('order-1')

    def test_ifood_cancellation_fetches_dynamic_reasons(self):
        api=IFood();x=SimpleNamespace(external_id='order-1')
        with patch.object(api,'request',side_effect=[[{'cancelCode':'503','description':'Indisponível'}],None]) as req:
            api.command(x,'cancelled',{'cancellationCode':'503','reason':'Teste'})
            self.assertEqual(req.call_args.kwargs['json'],{'reason':'503'})
        with patch.object(api,'request',return_value=[]):
            with self.assertRaises(ProviderError):api.command(x,'cancelled',{'cancellationCode':'999','reason':'Teste'})

    def test_temporary_own_order_item_total_without_order(self):
        from apps.orders.models import OrderItem
        self.assertEqual(OrderItem(price=Decimal('12.50'),quantity=2).get_total_price(),Decimal('25.00'))
    def test_worker_imports_ifood_details_through_adapter(self):
        e=receive(self.conn,{'id':'worker','orderId':self.dto['external_id'],'merchantId':self.conn.merchant_id,'code':'PLC','createdAt':self.t.isoformat()})
        with patch('apps.channels.connectors.IFood.detail',return_value=self.raw):process_event(e.pk)
        e.refresh_from_db();self.assertEqual(e.state,'processed');self.assertEqual(ExternalOrder.objects.get().financials['prepaid'],'49.90')
    def test_unknown_event_visible_for_manual_review(self):
        self.event();self.event('UNKNOWN_NEW_CONTRACT',offset=1)
        self.assertTrue(Inbox.objects.filter(state='ignored',error__contains='revisão').exists())
        self.assertIn('não suportado',ExternalOrder.objects.get().warning)
    def test_rate_limited_command_retries_with_backoff(self):
        x=self.event();self.conn.mode='test';self.conn.save()
        transition_order(order_id=x.order_id,tenant=self.a,target_status='confirmed')
        with patch('apps.channels.services.connector') as factory:
            factory.return_value.command.side_effect=ProviderError('Limite',retryable=True)
            cmd=Outbox.objects.get();process_command(cmd.pk)
        cmd.refresh_from_db();self.assertEqual(cmd.state,'pending');self.assertGreater(cmd.next_attempt,timezone.now())
    def test_final_event_supersedes_pending_cancellation(self):
        x=self.event('READY_TO_PICKUP');transition_order(order_id=x.order_id,tenant=self.a,target_status='cancelled',cancellation_code='SIM',cancellation_reason='Teste')
        self.event('CONCLUDED',offset=1)
        self.assertEqual(Outbox.objects.get().state,'superseded')
    def test_disconnected_history_stays_visible(self):
        x=self.event();self.conn.enabled=False;self.conn.save()
        data=self.client.get('/api/merchant/orders/').json();self.assertEqual(data['columns'][0]['orders'][0]['id'],x.order_id)
        self.assertEqual(data['columns'][0]['orders'][0]['allowed_transitions'],[])
    def test_rejected_cancellation_does_not_return_stock(self):
        x=self.event('CONFIRMED');transition_order(order_id=x.order_id,tenant=self.a,target_status='cancelled',cancellation_code='SIM',cancellation_reason='Teste')
        self.event('CANCELLATION_REQUEST_FAILED',offset=1)
        x.order.refresh_from_db();self.product.refresh_from_db()
        self.assertEqual(x.order.status,'confirmed');self.assertEqual(self.product.stock,9);self.assertEqual(Outbox.objects.get().state,'failed')
    @override_settings(CHANNELS_NETWORK_ENABLED=True,IFOOD_TEST_CLIENT_ID='fake',IFOOD_TEST_CLIENT_SECRET='fake')
    def test_live_remains_disabled_even_with_test_network(self):
        with patch('requests.request') as request:
            with self.assertRaises(ProviderError):IFood('live').token()
            request.assert_not_called()

    def test_event_endpoint_contract_and_ack_array(self):
        api=IFood()
        with patch.object(api,'request',return_value=[]) as request:
            api.poll(['merchant-a']);self.assertEqual(request.call_args.args[:2],('GET','/events/v1.0/events:polling'))
            api.acknowledge(['event-a']);self.assertEqual(request.call_args.args[:2],('POST','/events/v1.0/events/acknowledgment'));self.assertEqual(request.call_args.kwargs['json'],[{'id':'event-a'}])
    def test_not_found_details_stop_after_ten_minutes(self):
        e=receive(self.conn,{'id':'404','orderId':'gone','merchantId':self.conn.merchant_id,'code':'PLC','createdAt':self.t.isoformat()})
        Inbox.objects.filter(pk=e.pk).update(received_at=timezone.now()-timedelta(minutes=11))
        with patch('apps.channels.services.connector') as factory:
            factory.return_value.detail.side_effect=ProviderError('Indisponível',retryable=True,status_code=404)
            process_event(e.pk)
        e.refresh_from_db();self.assertEqual(e.state,'blocked')

    def test_scheduled_preparation_blocked_before_provider_time(self):
        d=deepcopy(self.dto);d['prepare_after']=(timezone.now()+timedelta(hours=1)).isoformat()
        o=self.event('CONFIRMED',dto=d).order
        self.assertEqual(allowed_transitions(o),['cancelled'])
        with self.assertRaises(OrderOperationError):transition_order(order_id=o.pk,tenant=self.a,target_status='preparing')
    def test_provider_fees_and_payment_balance_preserved(self):
        self.raw['total'].update(additionalFees=2,benefits=5,orderAmount=46.9)
        self.raw['payments'].update(prepaid=20,pending=26.9)
        x=self.event(dto=normalize_ifood(self.raw))
        self.assertEqual(x.order.total,Decimal('46.90'));self.assertEqual(x.order.discount_amount,Decimal('5.00'));self.assertEqual(x.financials,{'prepaid':'20.00','pending':'26.90','additional_fees':'2.00'})

# These require real row locking; SQLite must NOT be presented as this evidence.
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase,skipUnlessDBFeature

@override_settings(CHANNELS_SIMULATOR_ENABLED=True,CHANNELS_NETWORK_ENABLED=False)
class ChannelConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_delivery_creates_one_order_and_stock_movement(self):
        tenant=Tenant.objects.create(name='Concorrência',slug='concorrencia',whatsapp_number='5511999991111')
        c=Connection.objects.create(tenant=tenant,provider='ifood',mode='simulation',merchant_id='concurrent',enabled=True)
        category=Category.objects.create(tenant=tenant,name='Teste',slug='teste')
        p=Product.objects.create(tenant=tenant,category=category,name='Teste',slug='teste',price=10,stock=10)
        ProductLink.objects.create(connection=c,external_code='DEMO-LANCHE',product=p)
        payload=sample(c);barrier=Barrier(2)
        def run(n):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                e=receive(c,{'id':'same','orderId':payload['external_id'],'merchantId':c.merchant_id,'code':'CONFIRMED','createdAt':timezone.now().isoformat()})
                apply_event(e.pk,normalized=payload)
            finally:close_old_connections()
        with patch('apps.orders.signals.publish_order_event'),ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(run,[1,2]))
        self.assertEqual(Order.objects.count(),1);self.assertEqual(Inbox.objects.count(),1)
        p.refresh_from_db();self.assertEqual(p.stock,9);self.assertEqual(StockReservation.objects.count(),1)
