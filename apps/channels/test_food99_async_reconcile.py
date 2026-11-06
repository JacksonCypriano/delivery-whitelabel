"""No external calls, no Celery broker, no remote provider writes."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.channels.connectors import ProviderError
from apps.channels.food99_async_reconcile import (
    queue_reconciliation, reconcile_one, select_event_ids,
)

HML = dict(
    SETTINGS_MODULE="config.settings.hml",
    FOOD99_SANDBOX_ENABLED=True,
    CHANNELS_LIVE_ENABLED=False,
    CHANNELS_NETWORK_ENABLED=False,
    FOOD99_ASYNC_RECONCILE_ENABLED=True,
)


@override_settings(**HML)
class Food99AsyncReconcileTests(SimpleTestCase):
    @override_settings(FOOD99_ASYNC_RECONCILE_ENABLED=False)
    def test_disabled_by_default_fails_closed(self):
        with self.assertRaises(ProviderError):
            queue_reconciliation(tenant_slug="vitrine-demo")

    @override_settings(SETTINGS_MODULE="config.settings.prod")
    def test_production_is_always_closed(self):
        with self.assertRaises(ProviderError):
            reconcile_one(1)

    @override_settings(CHANNELS_LIVE_ENABLED=True)
    def test_live_mode_is_always_closed(self):
        with self.assertRaises(ProviderError):
            reconcile_one(1)

    def test_bad_limit_never_queries_db(self):
        for limit in (0, 101, True, "10"):
            with self.assertRaises(ProviderError):
                select_event_ids(tenant_slug="vitrine-demo", limit=limit)

    def test_blank_tenant_is_rejected(self):
        with self.assertRaises(ProviderError):
            select_event_ids(tenant_slug="")

    @patch("apps.channels.food99_async_reconcile.select_event_ids", return_value=[2, 5])
    def test_preview_queues_nothing(self, select):
        result = queue_reconciliation(tenant_slug="vitrine-demo")
        self.assertEqual(result["event_ids"], [2, 5])
        self.assertEqual(result["queued"], 0)
        self.assertFalse(result["acknowledged"])

    @patch("apps.channels.food99_async_reconcile.select_event_ids", return_value=[2, 5])
    def test_explicit_queue_is_bounded_and_has_no_ack(self, select):
        seen = []
        result = queue_reconciliation(tenant_slug="vitrine-demo", enqueue=seen.append)
        self.assertEqual(seen, [2, 5])
        self.assertEqual(result["queued"], 2)
        self.assertFalse(result["acknowledged"])

    @patch("apps.channels.food99_async_reconcile.select_event_ids", return_value=[2])
    def test_broker_failure_is_not_silenced(self, select):
        def down(_):
            raise RuntimeError("broker unavailable")
        with self.assertRaises(RuntimeError):
            queue_reconciliation(tenant_slug="vitrine-demo", enqueue=down)

    @patch("apps.channels.food99_async_reconcile.reconcile")
    def test_task_delegates_only_to_safe_existing_reconciliation(self, reconcile):
        reconcile.return_value = {"event_id": 5, "state": "UNCHANGED", "staged": True}
        result = reconcile_one(5)
        reconcile.assert_called_once_with(5, apply=True)
        self.assertEqual(result, {"event_id": 5, "state": "UNCHANGED", "staged": True,
                                  "acknowledged": False, "operational": False})
