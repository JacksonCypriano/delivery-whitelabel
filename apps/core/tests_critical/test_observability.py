from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings

from .base import CriticalTestCase


class ObservabilityCriticalTests(CriticalTestCase):
    def test_liveness_returns_200_and_request_id(self):
        response = self.client.get("/health/live/", HTTP_HOST="vemdedelivery.com.br")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertTrue(response.headers["X-Request-ID"])

    def test_safe_incoming_request_id_is_preserved(self):
        response = self.client.get("/health/live/", HTTP_HOST="vemdedelivery.com.br", HTTP_X_REQUEST_ID="critical-test-123")
        self.assertEqual(response.headers["X-Request-ID"], "critical-test-123")

    def test_invalid_incoming_request_id_is_replaced(self):
        response = self.client.get("/health/live/", HTTP_HOST="vemdedelivery.com.br", HTTP_X_REQUEST_ID="invalid request id !!!")
        self.assertNotEqual(response.headers["X-Request-ID"], "invalid request id !!!")
        self.assertTrue(response.headers["X-Request-ID"])

    def test_readiness_returns_200_when_dependencies_are_healthy(self):
        response = self.client.get("/health/ready/", HTTP_HOST="vemdedelivery.com.br")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"], {"database": True, "redis": True})

    def test_readiness_returns_503_when_cache_is_unavailable(self):
        with patch.object(cache, "set", side_effect=RuntimeError("cache unavailable")):
            response = self.client.get("/health/ready/", HTTP_HOST="vemdedelivery.com.br")
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json()["checks"]["database"])
        self.assertFalse(response.json()["checks"]["redis"])
