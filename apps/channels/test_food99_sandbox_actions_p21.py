"""Pacote 21: sandbox remote action guards and response contracts."""
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from apps.channels.food99_sandbox_actions import permitted_sandbox, queue_sandbox_transition, send_reserved_action
from apps.channels.models import Connection, ExternalOrder, Outbox
from apps.orders.models import Order
from apps.orders.operations import OrderOperationError
from apps.tenants.models import Tenant

FLAGS = dict(SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
             FOOD99_SANDBOX_ACTIONS_ENABLED=True, FOOD99_WEBHOOK_CAPTURE_ENABLED=True,
             FOOD99_WEBHOOK_ACK_ENABLED=True, FOOD99_ASYNC_RECONCILE_ENABLED=True,
             FOOD99_LOCAL_EVENT_SYNC_ENABLED=True, FOOD99_PILOT_TENANT_SLUG='vitrine-demo',
             CHANNELS_LIVE_ENABLED=False, CHANNELS_NETWORK_ENABLED=False)

@override_settings(**FLAGS)
class SandboxActionsTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Vitrine', slug='vitrine-demo', whatsapp_number='5511999991111')
        self.connection = Connection.objects.create(tenant=self.tenant, provider='99food', mode='test',
                                                     merchant_id='5764619171284910575', enabled=False)
        self.order = Order.objects.create(tenant=self.tenant, source='99food', status='confirmed',
                                          customer_name='Sandbox', total='25', subtotal='25',
                                          delivery_type='delivery', payment_flow='marketplace', payment_method='online')
        self.x = ExternalOrder.objects.create(connection=self.connection, order=self.order,
                        external_id='5764698537635941043', delivery_by='MERCHANT', encrypted_snapshot='sandbox')

    def test_actions_disabled_by_default(self):
        with override_settings(FOOD99_SANDBOX_ACTIONS_ENABLED=False):
            self.assertEqual(permitted_sandbox(self.order), [])

    def test_local_preparation_does_not_enqueue_provider(self):
        self.assertIn('preparing', permitted_sandbox(self.order))
        queue_sandbox_transition(self.order.pk, self.tenant, 'preparing')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'preparing')
        self.assertFalse(Outbox.objects.exists())

    def test_ready_is_reserved_and_not_repeated(self):
        with patch('apps.channels.tasks.send_99food_sandbox_action.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                queue_sandbox_transition(self.order.pk, self.tenant, 'ready')
        cmd = Outbox.objects.get()
        self.assertEqual(cmd.payload['food99_sandbox_action'], 'ready')
        self.assertEqual(cmd.state, 'pending')
        delay.assert_called_once_with(cmd.pk)
        with self.assertRaises(OrderOperationError):
            queue_sandbox_transition(self.order.pk, self.tenant, 'ready')

    def test_cancel_other_requires_details(self):
        with self.assertRaises(OrderOperationError):
            queue_sandbox_transition(self.order.pk, self.tenant, 'cancelled', payload={'cancellationCode': '1080'})

    def test_send_ready_post_once_and_waits_webhook(self):
        cmd = Outbox.objects.create(external_order=self.x, target='ready', from_status='confirmed',
                    payload={'food99_sandbox_action': 'ready'}, state='pending')
        detail = {'status': 200, 'cancel_time': 0, 'complete_time': 0}
        with patch('apps.channels.food99_orders.get_order_detail', return_value=detail), \
             patch('apps.channels.food99_auth.get_shop_token', return_value='fake'), \
             patch('requests.post', return_value=Mock(status_code=200, json=lambda: {'errno':0,'data':{}})) as post:
            # Import of functions happens inside sender. Patch import sources.
            result = send_reserved_action(cmd.pk)
            self.assertEqual(result['result'], 'AWAITING_WEBHOOK')
            self.assertEqual(send_reserved_action(cmd.pk)['sent'], False)
            post.assert_called_once()
        cmd.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(cmd.state, 'awaiting')
        self.assertEqual(self.order.status, 'confirmed')

    def test_platform_delivery_cannot_mark_delivered(self):
        self.x.delivery_by = 'PLATFORM'
        self.x.save(update_fields=['delivery_by'])
        self.order.status = 'ready'
        self.order.save(update_fields=['status'])
        self.assertNotIn('delivered', permitted_sandbox(self.order))

    def test_cancellation_reason_validated_before_outbox(self):
        with self.assertRaises(OrderOperationError):
            queue_sandbox_transition(self.order.pk, self.tenant, 'cancelled',
                                     payload={'cancellationCode': '9999'})
        self.assertFalse(Outbox.objects.exists())

    def test_failed_remote_response_is_uncertain_never_replayed(self):
        cmd = Outbox.objects.create(external_order=self.x, target='ready', from_status='confirmed',
                    payload={'food99_sandbox_action': 'ready'}, state='pending')
        with patch('apps.channels.food99_orders.get_order_detail', return_value={
                'status':200, 'cancel_time':0, 'complete_time':0}), \
             patch('apps.channels.food99_auth.get_shop_token', return_value='fake'), \
             patch('requests.post', return_value=Mock(status_code=500)) as post:
            self.assertEqual(send_reserved_action(cmd.pk)['result'], 'UNCERTAIN')
            self.assertEqual(send_reserved_action(cmd.pk)['sent'], False)
            post.assert_called_once()
        cmd.refresh_from_db()
        self.assertEqual(cmd.state, 'uncertain')
