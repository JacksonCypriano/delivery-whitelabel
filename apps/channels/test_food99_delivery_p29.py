"""Package 29: sandbox delivery diagnosis, read-only and scoped per tenant."""
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.channels.connectors import ProviderError
from apps.channels.food99_delivery_audit import audit_delivery
from apps.channels.models import Connection, ExternalOrder, Inbox, Outbox
from apps.orders.models import Order
from apps.tenants.models import Tenant

FLAGS = dict(SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
             CHANNELS_LIVE_ENABLED=False, CHANNELS_NETWORK_ENABLED=False)


@override_settings(**FLAGS)
class Food99DeliveryP29Tests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Entrega A', slug='p29-a', whatsapp_number='5511999991111')
        self.other = Tenant.objects.create(name='Entrega B', slug='p29-b', whatsapp_number='5511999992222')
        self.conn = Connection.objects.create(tenant=self.tenant, provider='99food',
                                              mode='test', merchant_id='p29-shop-a', enabled=False)
        self.order = Order.objects.create(tenant=self.tenant, source='99food', status='out_for_delivery',
                                          customer_name='Teste', total='10', subtotal='10',
                                          delivery_type='delivery', payment_flow='marketplace', payment_method='online')
        self.external = ExternalOrder.objects.create(connection=self.conn, order=self.order,
                                                     external_id='5764698886316820920', delivery_by='MERCHANT',
                                                     encrypted_snapshot='fixture')

    def test_awaiting_delivery_is_not_complete_and_has_no_side_effects(self):
        Outbox.objects.create(external_order=self.external, target='delivered',
                              from_status='out_for_delivery', state='awaiting', attempts=1,
                              payload={'food99_sandbox_action': 'delivered'}, sent_at=timezone.now())
        with patch('requests.post') as post, patch('requests.get') as get:
            report = audit_delivery(tenant_slug=self.tenant.slug, order_id=self.external.external_id)
        self.assertEqual(report['assessment'], 'AGUARDANDO_CONFIRMACAO_OFICIAL')
        self.assertFalse(report['finish_webhook_processed'])
        self.assertEqual(report['provider_writes'], 0)
        self.assertEqual(report['delivery_command']['attempts'], 1)
        self.assertEqual(self.order.status, 'out_for_delivery')
        post.assert_not_called(); get.assert_not_called()

    def test_foreign_tenant_blocked(self):
        with self.assertRaises(ProviderError):
            audit_delivery(tenant_slug=self.other.slug, order_id=self.external.external_id)

    def test_finished_webhook_is_not_enough_to_mutate_order(self):
        Inbox.objects.create(connection=self.conn, external_id='p29-event',
                             order_id=self.external.external_id, code='orderFinish',
                             occurred_at=timezone.now(), state='processed')
        report = audit_delivery(tenant_slug=self.tenant.slug, order_id=self.external.external_id)
        self.assertTrue(report['finish_webhook_processed'])
        self.assertEqual(report['assessment'], 'SEM_COMPROVACAO_DE_ENTREGA')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'out_for_delivery')

    @override_settings(CHANNELS_LIVE_ENABLED=True)
    def test_live_mode_rejected(self):
        with self.assertRaises(ProviderError):
            audit_delivery(tenant_slug=self.tenant.slug, order_id=self.external.external_id)

    def test_invalid_external_id_rejected(self):
        with self.assertRaises(ProviderError):
            audit_delivery(tenant_slug=self.tenant.slug, order_id='../../secret')
