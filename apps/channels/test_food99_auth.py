from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from .connectors import ProviderError
from .food99_auth import _call, _configuration, _expires_at


class Food99AuthUnitTests(SimpleTestCase):
    def test_denied_by_default(self):
        with override_settings(FOOD99_SANDBOX_ENABLED=False):
            with self.assertRaises(ProviderError):
                _configuration("vdd-vitrine-demo")

    @override_settings(FOOD99_SANDBOX_ENABLED=True, FOOD99_TEST_APP_ID="5764607657502050380", FOOD99_TEST_APP_SECRET="example-only")
    def test_valid_configuration(self):
        self.assertEqual(_configuration("vdd-vitrine-demo")[0], "5764607657502050380")

    def test_epoch_seconds_and_milliseconds(self):
        seconds = int((timezone.now() + timedelta(hours=2)).timestamp())
        self.assertEqual(_expires_at(seconds), _expires_at(seconds * 1000))

    def test_expired_token_rejected(self):
        with self.assertRaises(ProviderError):
            _expires_at(int((timezone.now() - timedelta(hours=1)).timestamp()))

    @patch("apps.channels.food99_auth.requests.get")
    def test_get_request_does_not_forward_private_server_error(self, get):
        get.return_value.status_code = 401
        get.return_value.text = "private-secret-in-error"
        with self.assertRaises(ProviderError) as error:
            _call("/v1/auth/authtoken/get", "123", "secret", "shop")
        self.assertNotIn("private-secret", str(error.exception))
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
