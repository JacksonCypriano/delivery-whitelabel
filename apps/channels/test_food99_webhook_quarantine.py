"""99Food callback quarantine tests: no external HTTP, payments or order creation."""
import hashlib
import json
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings

from apps.channels.models import Connection, Inbox, Outbox, ExternalOrder
from apps.channels.webhook_99food import food99_webhook
from apps.orders.models import Order
from apps.tenants.models import Tenant

SECRET = "test-secret-quarantine"
APP_ID = "5764607646131290647"
URL = "/integracoes/99food/test/webhook/"


@override_settings(
    SETTINGS_MODULE="config.settings.hml",
    FOOD99_SANDBOX_ENABLED=True,
    FOOD99_TEST_APP_SECRET=SECRET,
    FOOD99_TEST_APP_ID=APP_ID,
    FOOD99_WEBHOOK_CAPTURE_ENABLED=True,
    CHANNELS_LIVE_ENABLED=False,
)
class Food99WebhookQuarantineTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.tenant = Tenant.objects.create(
            slug="test-food99-quarantine", name="Test Food99 Quarantine",
            whatsapp_number="5511999990000",
        )
        self.conn = Connection.objects.create(
            tenant=self.tenant, provider="99food", mode="test",
            enabled=False, merchant_id="5764619171284910575",
        )
        self.payload = {
            "app_id": int(APP_ID),
            "app_shop_id": "vdd-test-food99-quarantine",
            "timestamp": 1793735606,
            "type": "orderNew",
            "data": {"order_id": 5764698533651349996,
                     "order_info": {"order_id": 5764698533651349996,
                                    "receive_address": {"name": "DO NOT PERSIST"}}},
        }

    def post(self, payload=None, *, valid_signature=True, raw=None):
        raw = raw if raw is not None else json.dumps(
            self.payload if payload is None else payload,
            separators=(",", ":"),
        ).encode()
        signature = hashlib.md5(raw + SECRET.encode()).hexdigest()
        if not valid_signature:
            signature = "0" * 32
        request = self.factory.post(
            URL, data=raw, content_type="application/json",
            HTTP_DIDI_HEADER_SIGN=signature,
        )
        return food99_webhook(request, "test")

    def test_valid_signed_webhook_is_durable_but_not_acknowledged(self):
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content)["errno"], 1)
        item = Inbox.objects.get()
        self.assertEqual(item.state, "blocked")
        self.assertEqual(item.code, "orderNew")
        self.assertEqual(item.order_id, "5764698533651349996")
        self.assertTrue(item.payload["food99_quarantined"])
        self.assertNotIn("DO NOT PERSIST", str(item.payload))
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Outbox.objects.count(), 0)
        self.assertEqual(ExternalOrder.objects.count(), 0)

    def test_identical_retries_are_idempotent(self):
        self.assertEqual(self.post().status_code, 503)
        self.assertEqual(self.post().status_code, 503)
        self.assertEqual(Inbox.objects.count(), 1)

    def test_distinct_signed_observations_remain_distinct(self):
        self.post()
        data = dict(self.payload, timestamp=self.payload["timestamp"] + 2)
        self.post(data)
        self.assertEqual(Inbox.objects.count(), 2)

    def test_invalid_signature_cannot_write(self):
        self.assertEqual(self.post(valid_signature=False).status_code, 401)
        self.assertEqual(Inbox.objects.count(), 0)

    def test_wrong_app_cannot_write(self):
        self.assertEqual(self.post(dict(self.payload, app_id=123)).status_code, 403)
        self.assertEqual(Inbox.objects.count(), 0)

    def test_foreign_store_cannot_write(self):
        self.assertEqual(self.post(dict(self.payload, app_shop_id="vdd-foreign")).status_code, 403)
        self.assertEqual(Inbox.objects.count(), 0)

    def test_id_mismatch_cannot_write(self):
        data = dict(self.payload, data={"order_id": 5764698533651349996,
                                       "order_info": {"order_id": 5764698533651349997}})
        self.assertEqual(self.post(data).status_code, 400)
        self.assertEqual(Inbox.objects.count(), 0)

    def test_disabled_capture_preserves_legacy_behavior(self):
        with override_settings(FOOD99_WEBHOOK_CAPTURE_ENABLED=False):
            response = self.post()
        # The endpoint may fail closed as unavailable (404) or unavailable
        # for processing (503). Neither response acknowledges the callback.
        self.assertIn(response.status_code, (404, 503))
        self.assertNotEqual(json.loads(response.content)["errno"], 0)
        self.assertEqual(Inbox.objects.count(), 0)

    def test_database_failure_never_acknowledges(self):
        from django.db import DatabaseError
        with patch("apps.channels.webhook_99food.Inbox.objects.get_or_create", side_effect=DatabaseError("private")):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", response.content.decode())

    def test_live_mode_remains_closed(self):
        response = food99_webhook(self.factory.post(URL), "live")
        self.assertEqual(response.status_code, 404)
