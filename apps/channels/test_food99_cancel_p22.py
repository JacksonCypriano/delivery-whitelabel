"""Pacote 22: motivos sandbox e limpeza após webhook terminal."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.channels.food99_local_sync import sync_existing
from apps.channels.models import Connection, ExternalOrder, Inbox, Outbox
from apps.channels.views import CancellationReasons
from apps.orders.models import Order
from apps.tenants.models import Tenant

FLAGS = dict(
    SETTINGS_MODULE='config.settings.hml',
    FOOD99_SANDBOX_ENABLED=True,
    FOOD99_SANDBOX_ACTIONS_ENABLED=True,
    FOOD99_WEBHOOK_CAPTURE_ENABLED=True,
    FOOD99_WEBHOOK_ACK_ENABLED=True,
    FOOD99_ASYNC_RECONCILE_ENABLED=True,
    FOOD99_LOCAL_EVENT_SYNC_ENABLED=True,
    FOOD99_SANDBOX_IMPORT_TO_ORDERS=True,
    FOOD99_PILOT_TENANT_SLUG='vitrine-demo',
    CHANNELS_LIVE_ENABLED=False,
    CHANNELS_NETWORK_ENABLED=False,
)


@override_settings(**FLAGS)
class CancellationSandboxP22Tests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Vitrine', slug='vitrine-demo', whatsapp_number='5511999991111')
        self.conn = Connection.objects.create(
            tenant=self.tenant, provider='99food', mode='test',
            merchant_id='5764619171284910575', enabled=False)
        self.order = Order.objects.create(
            tenant=self.tenant, source='99food', status='confirmed',
            customer_name='Sandbox', total='25', subtotal='25',
            delivery_type='delivery', payment_flow='marketplace', payment_method='online')
        self.x = ExternalOrder.objects.create(
            connection=self.conn, order=self.order,
            external_id='5764698562860485480', delivery_by='MERCHANT',
            encrypted_snapshot='sandbox')

    def reasons(self):
        return CancellationReasons().get(SimpleNamespace(tenant=self.tenant), self.order.pk)

    def test_sandbox_connected_false_can_show_official_reasons(self):
        response = self.reasons()
        self.assertEqual(response.status_code, 200)
        codes = {item['code'] for item in response.data['reasons']}
        self.assertEqual(codes, {str(x) for x in (1010,1020,1030,1040,1050,1060,1070,1071,1072,1073,1074,1080)})

    def test_platform_does_not_show_self_delivery_reasons(self):
        self.x.delivery_by = 'PLATFORM'
        self.x.save(update_fields=['delivery_by'])
        response = self.reasons()
        self.assertEqual(response.status_code, 200)
        codes = {item['code'] for item in response.data['reasons']}
        self.assertFalse({'1060', '1071', '1072'} & codes)

    def test_disabling_sandbox_actions_closes_reasons_endpoint(self):
        with override_settings(FOOD99_SANDBOX_ACTIONS_ENABLED=False):
            self.assertEqual(self.reasons().status_code, 409)

    def test_other_tenant_cannot_see_reasons(self):
        other = Tenant.objects.create(name='Outro', slug='outro', whatsapp_number='5511999992222')
        response = CancellationReasons().get(SimpleNamespace(tenant=other), self.order.pk)
        self.assertEqual(response.status_code, 404)

    def test_cancel_pending_command_blocks_reasons(self):
        Outbox.objects.create(external_order=self.x, target='cancelled',
                              from_status='confirmed', state='awaiting')
        self.assertEqual(self.reasons().status_code, 409)

    def make_event(self):
        digest = 'a' * 64
        return Inbox.objects.create(
            connection=self.conn, external_id='99food-' + digest,
            order_id=self.x.external_id, code='orderCancel',
            occurred_at=timezone.now(), state='blocked',
            payload={
                'food99_quarantined': True,
                'operational_enabled': False,
                'raw_sha256': digest,
                'app_shop_id': 'vdd-vitrine-demo',
            },
        )

    def test_order_cancel_clears_pending_and_confirms_outbox(self):
        self.x.cancellation_state = 'requested'
        self.x.cancellation_error = 'antigo'
        self.x.cancellation_requested_at = timezone.now() - timedelta(minutes=2)
        self.x.save(update_fields=['cancellation_state', 'cancellation_error', 'cancellation_requested_at'])
        cmd = Outbox.objects.create(external_order=self.x, target='cancelled',
                                    from_status='confirmed', state='awaiting')
        event = self.make_event()
        with patch('apps.channels.food99_local_sync.publish_order_event'):
            result = sync_existing(event.pk, apply=True)
        self.assertEqual(result['result'], 'UPDATED')
        self.order.refresh_from_db()
        self.x.refresh_from_db()
        cmd.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')
        self.assertEqual(self.x.cancellation_state, '')
        self.assertEqual(self.x.cancellation_error, '')
        self.assertIsNone(self.x.cancellation_requested_at)
        self.assertEqual(cmd.state, 'confirmed')
        self.assertEqual(self.reasons().status_code, 409)

    def test_terminal_no_change_also_clears_pending(self):
        self.order.status = 'cancelled'
        self.order.save(update_fields=['status'])
        self.x.cancellation_state = 'requested'
        self.x.save(update_fields=['cancellation_state'])
        cmd = Outbox.objects.create(external_order=self.x, target='cancelled',
                                    from_status='confirmed', state='awaiting')
        event = self.make_event()
        result = sync_existing(event.pk, apply=True)
        self.assertEqual(result['result'], 'NO_CHANGE')
        self.x.refresh_from_db()
        cmd.refresh_from_db()
        self.assertEqual(self.x.cancellation_state, '')
        self.assertEqual(cmd.state, 'confirmed')
