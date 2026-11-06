"""Pure callback contract tests. No 99Food network requests are made."""
import hashlib
import json
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings

from apps.channels.webhook_99food import food99_webhook, verify_signature
from apps.channels.models import Connection
from apps.tenants.models import Tenant

URL = "/integracoes/99food/test/webhook/"
SECRET = "only-a-test-secret"
APP_ID = "5764607646131290647"


@override_settings(
    SETTINGS_MODULE="config.settings.hml",
    FOOD99_SANDBOX_ENABLED=True,
    FOOD99_TEST_APP_SECRET=SECRET,
    FOOD99_TEST_APP_ID=APP_ID,
    CHANNELS_LIVE_ENABLED=False,
    FOOD99_WEBHOOK_CAPTURE_ENABLED=False,
)
class Food99WebhookContractTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        tenant = Tenant.objects.create(
            slug="vitrine-demo", name="Test Webhook Contract",
            whatsapp_number="5511999990000",
        )
        Connection.objects.create(
            tenant=tenant, provider="99food", mode="test",
            enabled=False, merchant_id="5764619171284910575",
        )
        self.payload = {
            "app_id": int(APP_ID), "app_shop_id": "vdd-vitrine-demo",
            "timestamp": 1793735606, "type": "orderNew",
            "data": {"order_id": 5764698533651349996},
        }

    def post(self, payload=None, *, signature=True, body=None):
        raw = body if body is not None else json.dumps(
            self.payload if payload is None else payload, separators=(",", ":")
        ).encode("utf-8")
        header = hashlib.md5(raw + SECRET.encode()).hexdigest() if signature else "invalid"
        request = self.factory.post(URL, data=raw, content_type="application/json",
                                    HTTP_DIDI_HEADER_SIGN=header)
        return food99_webhook(request, "test")

    def test_documented_md5_of_raw_body_and_secret(self):
        body = b'{"hello":"world"}'
        digest = hashlib.md5(body + SECRET.encode()).hexdigest()
        self.assertTrue(verify_signature(body, digest, SECRET))
        self.assertTrue(verify_signature(body, digest.upper(), SECRET))
        self.assertFalse(verify_signature(body + b" ", digest, SECRET))
        self.assertFalse(verify_signature(body, "broken", SECRET))

    def test_invalid_signature_never_reaches_db(self):
        with patch("apps.channels.webhook_99food.Connection.objects.filter") as query:
            response = self.post(signature=False)
        self.assertEqual(response.status_code, 401)
        query.assert_not_called()

    def test_signed_order_still_not_acknowledged_before_durable_storage(self):
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content)["errno"], 1)
        self.assertEqual(response["Retry-After"], "300")

    def test_signed_wrong_app_is_rejected(self):
        data = dict(self.payload, app_id=123)
        self.assertEqual(self.post(data).status_code, 403)

    def test_signed_unknown_shop_is_rejected(self):
        response = self.post(dict(self.payload, app_shop_id="vdd-foreign"))
        self.assertEqual(response.status_code, 403)

    def test_unknown_event_is_not_acknowledged(self):
        response = self.post(dict(self.payload, type="newEvent"))
        self.assertEqual(response.status_code, 503)

    def test_live_mode_is_closed(self):
        self.assertEqual(food99_webhook(self.factory.post(URL), "live").status_code, 404)

    def test_bad_json_with_valid_signature_is_rejected(self):
        self.assertEqual(self.post(body=b"{broken").status_code, 400)

    def test_body_size_limit(self):
        self.assertEqual(self.post(body=b"x" * 131073).status_code, 413)

    def test_head_and_get_remain_registration_only(self):
        self.assertFalse(json.loads(food99_webhook(self.factory.get(URL), "test").content)["events_enabled"])
        self.assertEqual(food99_webhook(self.factory.head(URL), "test").content, b"")
