"""Celery task delegates only to the guarded, local-only sandbox projector."""
from unittest.mock import patch
from django.test import SimpleTestCase
from apps.channels.tasks import sync_99food_sandbox_events


class Food99SandboxEventTaskTests(SimpleTestCase):
    @patch('apps.channels.food99_local_sync.sync_batch')
    def test_task_uses_explicit_tenant_and_guarded_apply(self, sync):
        sync.return_value = {'selected': 0, 'updated': 0, 'events': [], 'applied': True}
        result = sync_99food_sandbox_events.run('vitrine-demo', 10)
        sync.assert_called_once_with(tenant_slug='vitrine-demo', limit=10, apply=True)
        self.assertEqual(result['updated'], 0)
