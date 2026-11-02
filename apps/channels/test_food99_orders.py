"""Isolated tests: no outbound calls to 99Food."""
from unittest.mock import patch, Mock
from django.test import SimpleTestCase, override_settings
from apps.channels.connectors import ProviderError
from apps.channels.food99_orders import get_order_detail


@override_settings(FOOD99_SANDBOX_ENABLED=True)
class ReadOnlyOrderTests(SimpleTestCase):
    @patch('apps.channels.food99_orders.get_shop_token', return_value='private-test-token')
    @patch('apps.channels.food99_orders.requests.get')
    def test_order_details(self, get, token):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {"errno": 0, "data": {"order_id": 123}}
        self.assertEqual(get_order_detail('vdd-vitrine-demo', '123'), {"order_id": 123})
        self.assertEqual(get.call_args.kwargs['params']['order_id'], '123')
        self.assertFalse(get.call_args.kwargs['allow_redirects'])

    @patch('apps.channels.food99_orders.requests.get')
    def test_invalid_id_never_calls_network(self, get):
        with self.assertRaises(ProviderError):
            get_order_detail('vdd-vitrine-demo', 'not-an-id')
        get.assert_not_called()

    @patch('apps.channels.food99_orders.get_shop_token', return_value='private-test-token')
    @patch('apps.channels.food99_orders.requests.get')
    def test_api_rejection(self, get, token):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {"errno": 2, "errmsg": "sensitive-provider-info"}
        with self.assertRaisesRegex(ProviderError, 'recusou') as raised:
            get_order_detail('vdd-vitrine-demo', '123')
        self.assertNotIn('sensitive-provider-info', str(raised.exception))

    @override_settings(FOOD99_SANDBOX_ENABLED=False)
    @patch('apps.channels.food99_orders.get_shop_token')
    def test_disabled_sandbox(self, token):
        with self.assertRaises(ProviderError):
            get_order_detail('vdd-vitrine-demo', '123')
        token.assert_not_called()
