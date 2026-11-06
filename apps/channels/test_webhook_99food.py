"""Registration-only webhook tests; not official 99Food certification."""

from django.test import SimpleTestCase
from django.urls import reverse


class Food99RegistrationWebhookTests(SimpleTestCase):
    def url(self, mode="test"):
        return reverse("food99_webhook", kwargs={"mode": mode})

    def test_get_is_only_a_readiness_probe_not_an_event_acknowledgment(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"provider": "99food", "mode": "test", "events_enabled": False},
        )
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_head_returns_no_body(self):
        response = self.client.head(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.content)

    def test_post_cannot_acknowledge_unverified_payload(self):
        # SimpleTestCase disallows database queries: untrusted events must not
        # reach Inbox/Orders before official signature validation exists.
        response = self.client.post(
            self.url(),
            data='{"orderId":"unverified-123","event":"PLACED"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "300")
        self.assertNotIn("received", response.json())

    def test_large_post_is_rejected(self):
        response = self.client.post(
            self.url(), data=b"x" * 131073,
            content_type="application/octet-stream",
        )
        self.assertEqual(response.status_code, 413)

    def test_live_and_simulation_webhooks_are_not_exposed(self):
        for mode in ("live", "simulation", "anything"):
            with self.subTest(mode=mode):
                self.assertEqual(self.client.get(self.url(mode)).status_code, 404)
                self.assertEqual(self.client.post(self.url(mode), data=b"{}", content_type="application/json").status_code, 404)

    def test_unsafe_methods_not_allowed(self):
        self.assertEqual(self.client.put(self.url(), data=b"{}").status_code, 405)
