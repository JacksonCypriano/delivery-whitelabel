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


from django.test import TestCase
from .models import AppToken
from .food99_auth import get_shop_token
from apps.billing.secrets import encrypt_secret


@override_settings(FOOD99_SANDBOX_ENABLED=True,
                   FOOD99_TEST_APP_ID="5764607657502050380",
                   FOOD99_TEST_APP_SECRET="example-only")
class Food99TokenLifecycleTests(TestCase):
    @patch("apps.channels.food99_auth._call")
    def test_missing_token_renews_before_get(self, call):
        expires = int((timezone.now() + timedelta(hours=2)).timestamp())
        call.side_effect = [True, {
            "app_id": "5764607657502050380",
            "app_shop_id": "vdd-vitrine-demo",
            "auth_token": "secret-token",
            "token_expiration_time": expires,
        }]
        self.assertEqual(get_shop_token("vdd-vitrine-demo"), "secret-token")
        self.assertEqual(call.call_args_list[0].args[0], "/v1/auth/authtoken/refresh")
        self.assertEqual(call.call_args_list[1].args[0], "/v1/auth/authtoken/get")
        stored = AppToken.objects.get()
        self.assertNotIn("secret-token", stored.encrypted_token)

    @patch("apps.channels.food99_auth._call")
    def test_valid_cached_token_does_not_call_api(self, call):
        import hashlib
        key = "99food:" + hashlib.sha256(("5764607657502050380:vdd-vitrine-demo").encode()).hexdigest()[:32]
        AppToken.objects.create(key=key, encrypted_token=encrypt_secret("cached-token"),
                                expires_at=timezone.now() + timedelta(hours=1))
        self.assertEqual(get_shop_token("vdd-vitrine-demo"), "cached-token")
        call.assert_not_called()

    @patch("apps.channels.food99_auth._call", return_value=False)
    def test_refresh_failure_never_falls_back_to_get(self, call):
        with self.assertRaisesRegex(ProviderError, "não confirmou renovação"):
            get_shop_token("vdd-vitrine-demo")
        self.assertEqual(call.call_count, 1)
