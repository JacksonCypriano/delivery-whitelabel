"""Operational boundaries, all provider IO mocked; never executed for delivery."""
from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase, override_settings
from .commercial import receive, process_message
from .commercial_api import CommercialPanel
from .commercial_models import CommercialControl, CommercialConversation, CommercialMessage


@override_settings(COMMERCIAL_AGENT_ENABLED=True)
class CommercialReleaseTests(TestCase):
    def setUp(self):
        self.control = CommercialControl.objects.create(enabled=True, instance='release-test')
        self.conv = CommercialConversation.objects.create(instance='release-test', phone='5599000000000')
        self.net = patch('requests.sessions.Session.request', side_effect=AssertionError('network forbidden')).start()
        self.addCleanup(patch.stopall)

    def queued(self, key='one'):
        return CommercialMessage.objects.create(conversation=self.conv, provider_id=key, text='quanto custa?', state='queued')

    def test_pause_holds_backlog_without_provider_calls(self):
        row = self.queued()
        response = CommercialPanel().post(SimpleNamespace(data={'action': 'pause'}, user=None))
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.state, 'held')
        self.control.refresh_from_db()
        self.assertFalse(self.control.enabled)
        self.net.assert_not_called()

    @override_settings(COMMERCIAL_AGENT_ENABLED=False)
    def test_disabled_server_receives_into_held_not_future_backlog(self):
        with patch('apps.prospecting.commercial.validate_instance'):
            row = receive('release-test', dict(message_id='off', phone=self.conv.phone,
                          text='oi', from_me=False, kind='text'))
        self.assertEqual(row.state, 'held')
        process_message(row.pk)
        self.net.assert_not_called()

    def test_human_takeover_holds_other_pending_messages(self):
        older = self.queued()
        with patch('apps.prospecting.commercial.validate_instance'):
            row = receive('release-test', dict(message_id='human', phone=self.conv.phone,
                          text='quero falar com pessoa', from_me=False, kind='text'))
        older.refresh_from_db()
        self.assertEqual(older.state, 'held')
        self.assertEqual(row.state, 'human')

    def test_uncertain_send_never_retries(self):
        row = self.queued()
        with patch('apps.prospecting.commercial.validate_instance'), \
             patch('apps.prospecting.commercial.published_catalog', return_value={'fingerprint': 'f'}), \
             patch('apps.prospecting.commercial.articles', return_value=[object()]), \
             patch('apps.prospecting.commercial.compose', return_value=('Resposta aprovada.', [])), \
             patch('apps.prospecting.commercial.TenantEvolutionClient') as client:
            client.return_value.status.return_value = 'open'
            client.return_value.send_text.side_effect = RuntimeError('failure')
            process_message(row.pk)
            process_message(row.pk)
            client.return_value.send_text.assert_called_once()
        row.refresh_from_db()
        self.assertEqual(row.state, 'uncertain')
        self.conv.refresh_from_db()
        self.assertTrue(self.conv.paused)
