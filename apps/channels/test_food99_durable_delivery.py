"""Fail-closed ACK and replay tests for signed sandbox event delivery."""
import hashlib
import json
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.channels.connectors import ProviderError
from apps.channels.food99_sandbox_consumer import consume_event
from apps.channels.models import Connection, Inbox
from apps.channels.tasks import consume_99food_sandbox_event
from apps.channels.webhook_99food import food99_webhook
from apps.tenants.models import Tenant


@override_settings(
    SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
    FOOD99_TEST_APP_ID='12345678901234567', FOOD99_TEST_APP_SECRET='test-secret',
    FOOD99_WEBHOOK_CAPTURE_ENABLED=True, FOOD99_WEBHOOK_ACK_ENABLED=True,
    FOOD99_ASYNC_RECONCILE_ENABLED=True, CHANNELS_LIVE_ENABLED=False,
    CHANNELS_NETWORK_ENABLED=False,
)
class Food99DurableDeliveryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        tenant = Tenant.objects.create(
            slug='durable-test', name='Durable Test', whatsapp_number='5511999912345',
        )
        self.conn = Connection.objects.create(
            tenant=tenant, provider='99food', mode='test', enabled=False,
            merchant_id='5764619171284910575',
        )
        self.event = {
            'app_id': 12345678901234567, 'app_shop_id': 'vdd-durable-test',
            'timestamp': 1793735606, 'type': 'orderNew',
            'data': {'order_id': 5764698533651349996,
                     'order_info': {'order_id': 5764698533651349996,
                                    'receive_address': {'name': 'DO-NOT-STORE'}}},
        }

    def post(self, event=None, *, valid=True):
        raw = json.dumps(event if event is not None else self.event).encode()
        sign = hashlib.md5(raw + b'test-secret').hexdigest() if valid else '0' * 32
        request = self.factory.post('/integracoes/99food/test/webhook/',
                                    data=raw, content_type='application/json',
                                    HTTP_DIDI_HEADER_SIGN=sign)
        return food99_webhook(request, 'test')

    @patch('apps.channels.tasks.consume_99food_sandbox_event.delay')
    def test_ack_only_after_durable_store(self, delay):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {'errno': 0, 'errmsg': 'ok'})
        event = Inbox.objects.get()
        self.assertEqual(event.order_id, '5764698533651349996')
        self.assertEqual(event.state, 'blocked')
        self.assertNotIn('DO-NOT-STORE', str(event.payload))
        delay.assert_called_once_with(event.pk)

    @patch('apps.channels.tasks.consume_99food_sandbox_event.delay')
    def test_exact_retry_requeues_without_duplicate(self, delay):
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(Inbox.objects.count(), 1)
        self.assertEqual(delay.call_count, 2)

    @patch('apps.channels.tasks.consume_99food_sandbox_event.delay', side_effect=RuntimeError('secret'))
    def test_broker_failure_never_returns_success(self, delay):
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', response.content.decode())
        self.assertEqual(Inbox.objects.count(), 1)

    @patch('apps.channels.tasks.consume_99food_sandbox_event.delay')
    def test_invalid_signature_never_queues(self, delay):
        self.assertEqual(self.post(valid=False).status_code, 401)
        self.assertEqual(Inbox.objects.count(), 0)
        delay.assert_not_called()

    @patch('apps.channels.tasks.consume_99food_sandbox_event.delay')
    def test_foreign_tenant_never_queues(self, delay):
        event = dict(self.event, app_shop_id='vdd-foreign')
        self.assertEqual(self.post(event).status_code, 403)
        delay.assert_not_called()

    @patch('apps.channels.tasks.consume_99food_sandbox_event.delay')
    @override_settings(SETTINGS_MODULE="config.settings.hml", FOOD99_SANDBOX_ENABLED=True, CHANNELS_LIVE_ENABLED=False, FOOD99_WEBHOOK_CAPTURE_ENABLED=False)
    def test_no_ack_without_capture(self, delay):
        self.assertEqual(self.post().status_code, 503)
        self.assertEqual(Inbox.objects.count(), 0)
        delay.assert_not_called()

    @patch('apps.channels.tasks.consume_99food_sandbox_event.delay')
    @override_settings(SETTINGS_MODULE="config.settings.hml", FOOD99_SANDBOX_ENABLED=True, CHANNELS_LIVE_ENABLED=False, FOOD99_ASYNC_RECONCILE_ENABLED=False)
    def test_no_ack_without_consumer(self, delay):
        self.assertEqual(self.post().status_code, 503)
        delay.assert_not_called()

    @patch('apps.channels.tasks.consume_99food_sandbox_event.delay')
    @override_settings(SETTINGS_MODULE="config.settings.hml", FOOD99_SANDBOX_ENABLED=True, CHANNELS_LIVE_ENABLED=False, FOOD99_WEBHOOK_ACK_ENABLED=False)
    def test_legacy_quarantine_response_unchanged(self, delay):
        self.assertEqual(self.post().status_code, 503)
        self.assertEqual(Inbox.objects.count(), 1)
        delay.assert_not_called()

    @patch('apps.channels.tasks.consume_99food_sandbox_event.delay')
    def test_no_ack_for_non_order_event(self, delay):
        event = dict(self.event, type='shopStatus')
        self.assertEqual(self.post(event).status_code, 503)
        delay.assert_not_called()


class Food99ConsumerTaskTests(SimpleTestCase):
    @patch('apps.channels.food99_sandbox_consumer.consume_event')
    def test_task_delegates(self, consume):
        consume.return_value = {'event_id': 7, 'result': 'STAGED_REVIEW_REQUIRED'}
        self.assertEqual(consume_99food_sandbox_event.run(7)['event_id'], 7)
        consume.assert_called_once_with(7)

    @patch('apps.channels.food99_sandbox_consumer._async_guard', side_effect=ProviderError('disabled'))
    def test_disabled_worker_rejects(self, guard):
        with self.assertRaises(ProviderError):
            consume_event(7)
