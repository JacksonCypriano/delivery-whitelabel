"""No provider writes. Promotion requires review, valid signed event and opt-in."""
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.channels.models import Connection, Inbox, Outbox, ExternalOrder, Food99StagedOrder
from apps.channels.food99_staging import stage_order
from apps.channels.food99_sandbox_promotion import promote_reviewed
from apps.channels.connectors import ProviderError
from apps.orders.models import Order


@override_settings(SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
                   CHANNELS_LIVE_ENABLED=False, CHANNELS_NETWORK_ENABLED=False,
                   FOOD99_SANDBOX_IMPORT_TO_ORDERS=False)
class Food99PromotionTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Promo Sandbox', slug='promo-sandbox',
                                             whatsapp_number='5511999990000')
        self.conn = Connection.objects.create(tenant=self.tenant, provider='99food',
                     mode='test', enabled=False, merchant_id='123456789')
        self.order_id = '5764698533651349996'
        self.detail = {
            'order_id':int(self.order_id), 'status':100,
            'shop':{'shop_id':123456789, 'app_shop_id':'vdd-promo-sandbox'},
            'create_time':int(timezone.now().timestamp()), 'cancel_time':0,
            'complete_time':0, 'delivery_type':2, 'pay_type':1,
            'price':{'order_price':2100, 'real_pay_price':2100,
                     'delivery_price':100, 'items_discount':0,'delivery_discount':0},
            'order_items':[{'name':'Pizza', 'app_item_id':'PIZZA', 'amount':2,
                            'total_price':2000, 'sub_item_list':[{'name':'Queijo',
                            'amount':1,'total_price':100,'sub_item_list':[]}]}],
            'receive_address':{'name':'DADO PRIVADO','phone':'11999999999'},
        }
        self.row, _ = stage_order(self.detail, tenant=self.tenant,
                app_shop_id='vdd-promo-sandbox',shop_id=self.conn.merchant_id,
                order_id=self.order_id)
        self.row.state='reviewed'
        self.row.save(update_fields=['state'])
        sha='a'*64
        self.event=Inbox.objects.create(connection=self.conn, external_id='99food-'+sha,
            order_id=self.order_id, code='orderNew', state='blocked',
            occurred_at=timezone.now(), payload={'food99_quarantined':True,
                'app_shop_id':'vdd-promo-sandbox','operational_enabled':False,
                'raw_sha256':sha})

    def test_preview_does_not_import(self):
        result=promote_reviewed(staged_id=self.row.pk)
        self.assertTrue(result['eligible'])
        self.assertFalse(result['imported'])
        self.assertEqual(Order.objects.count(),0)

    def test_apply_without_optin_rejected(self):
        with self.assertRaises(ProviderError):
            promote_reviewed(staged_id=self.row.pk,apply=True,confirm_brl=True)
        self.assertEqual(Order.objects.count(),0)

    def test_apply_requires_explicit_currency_consent(self):
        with override_settings(FOOD99_SANDBOX_IMPORT_TO_ORDERS=True):
            with self.assertRaises(ProviderError):
                promote_reviewed(staged_id=self.row.pk,apply=True)

    def test_live_network_and_closed_connection(self):
        for flags in ({'CHANNELS_LIVE_ENABLED':True},
                      {'CHANNELS_NETWORK_ENABLED':True},
                      {'SETTINGS_MODULE':'config.settings.prod'}):
            with override_settings(**flags):
                with self.assertRaises(ProviderError):promote_reviewed(staged_id=self.row.pk)
        self.conn.enabled=True
        self.conn.save(update_fields=['enabled'])
        with self.assertRaises(ProviderError):promote_reviewed(staged_id=self.row.pk)

    def test_cancelled_and_unknown_status_rejected(self):
        for status in (922, 999):
            self.detail['status']=status
            self._restage()
            with self.assertRaises(ProviderError):promote_reviewed(staged_id=self.row.pk)
        self.detail['status']=100
        # A remote cancellation without a changed staged fingerprint must
        # still be caught by the mandatory fresh GET on apply.
        self.detail['cancel_time']=0
        self._restage()
        with override_settings(FOOD99_SANDBOX_IMPORT_TO_ORDERS=True), \
             patch('apps.channels.food99_sandbox_promotion.get_order_detail',
                   return_value={**self.detail, 'cancel_time':int(timezone.now().timestamp())}):
            with self.assertRaises(ProviderError):
                promote_reviewed(staged_id=self.row.pk,apply=True,confirm_brl=True)

    def _restage(self):
        self.row,_=stage_order(self.detail,tenant=self.tenant,
           app_shop_id='vdd-promo-sandbox',shop_id=self.conn.merchant_id,
           order_id=self.order_id)
        self.row.state='reviewed'
        self.row.save(update_fields=['state'])

    def test_expired_order_is_not_reactivated(self):
        # The reviewed snapshot is immutable when only create_time changes:
        # create_time is intentionally excluded from the semantic fingerprint.
        # Advance the clock instead to exercise the five-minute expiry guard.
        expired_clock = timezone.now() + timedelta(minutes=9)
        with patch('apps.channels.food99_sandbox_promotion.timezone.now',
                   return_value=expired_clock):
            with self.assertRaises(ProviderError):
                promote_reviewed(staged_id=self.row.pk)

    def test_no_signed_event_no_promotion(self):
        self.event.delete()
        with self.assertRaises(ProviderError):promote_reviewed(staged_id=self.row.pk)

    def test_no_review_no_promotion(self):
        self.row.state='review'
        self.row.save(update_fields=['state'])
        with self.assertRaises(ProviderError):promote_reviewed(staged_id=self.row.pk)

    def test_import_local_once_without_network_or_outbox(self):
        # Explicitly pin *all* isolation switches in the nested settings
        # override: a test run must not inherit an unsafe environment flag.
        with override_settings(
                SETTINGS_MODULE='config.settings.hml',
                FOOD99_SANDBOX_ENABLED=True,
                CHANNELS_LIVE_ENABLED=False,
                CHANNELS_NETWORK_ENABLED=False,
                FOOD99_SANDBOX_IMPORT_TO_ORDERS=True), \
             patch('apps.channels.food99_sandbox_promotion.get_order_detail',return_value=self.detail) as get:
            first=promote_reviewed(staged_id=self.row.pk,apply=True,confirm_brl=True)
            again=promote_reviewed(staged_id=self.row.pk,apply=True,confirm_brl=True)
            get.assert_called_once()
        self.assertTrue(first['imported'])
        self.assertFalse(again['imported'])
        self.assertTrue(again['existing'])
        self.assertEqual(Order.objects.filter(source='99food').count(),1)
        self.assertEqual(ExternalOrder.objects.count(),1)
        self.assertEqual(Outbox.objects.count(),0)
        obj=Order.objects.get()
        self.assertEqual(obj.status,'pending')
        self.assertEqual(obj.items.count(),1)
        self.assertFalse(self.conn.enabled)
        self.assertNotIn('11999999999',repr(first))
