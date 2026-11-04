from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from apps.channels.connectors import ProviderError
from apps.channels.tasks import reconcile_99food_quarantine_event


class Food99AsyncTaskTests(SimpleTestCase):
    @override_settings(FOOD99_ASYNC_RECONCILE_ENABLED=False)
    def test_disabled_worker_cannot_process(self):
        with self.assertRaises(ProviderError):
            reconcile_99food_quarantine_event.run(1)

    @patch("apps.channels.food99_async_reconcile.reconcile_one")
    def test_task_delegates_to_safe_processor(self, processor):
        processor.return_value = {"event_id": 7, "acknowledged": False, "operational": False}
        self.assertEqual(reconcile_99food_quarantine_event.run(7)["event_id"], 7)
        processor.assert_called_once_with(7)
