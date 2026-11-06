"""Smoke tests for command registration without a running broker."""
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import SimpleTestCase


class Queue99FoodCommandTests(SimpleTestCase):
    @patch("apps.channels.management.commands.queue_99food_webhook_reconcile.queue_reconciliation")
    def test_preview_does_not_queue(self, service):
        service.return_value = {"mode": "preview", "selected": 0, "queued": 0}
        stream = StringIO()
        call_command("queue_99food_webhook_reconcile", tenant="vitrine-demo", stdout=stream)
        self.assertIn("ACK=False", stream.getvalue())
        self.assertIsNone(service.call_args.kwargs["enqueue"])
