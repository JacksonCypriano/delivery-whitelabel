"""Regressões dos alertas operacionais. Escrito para CI; não executado no pacote."""
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .commercial import receive
from .commercial_api import CommercialPanel
from .commercial_models import (
    CommercialControl, CommercialConversation, CommercialHandoffAlert,
    CommercialMessage, CommercialOtpExclusion, CommercialPilotContact,
)
from .commercial_pilot import alert_human
from .tasks import dispatch_commercial_handoff_whatsapp_alerts


@override_settings(COMMERCIAL_AGENT_ENABLED=True)
class CommercialHumanNotificationTests(TestCase):
    def setUp(self):
        self.control = CommercialControl.objects.create(
            pk=1, instance='commercial-test', enabled=True,
            handoff_notify_phone='5511983491206', handoff_notify_enabled=True,
            handoff_notify_enabled_at=timezone.now(),
        )
        self.conv = CommercialConversation.objects.create(
            instance=self.control.instance, phone='5511999999999', paused=True,
        )
        self.row = CommercialMessage.objects.create(
            conversation=self.conv, provider_id='human-request',
            text='Quero um atendente', state='human',
        )
        CommercialPilotContact.objects.create(phone=self.conv.phone, active=True)
        self.alert = alert_human(self.conv, self.row, 'commercial_human_review_required')
        self.user = get_user_model().objects.create_superuser(
            'alert-admin', 'alert-admin@example.com', 'testpass123',
        )

    def test_dispatch_contains_whatsapp_link_and_does_not_retry(self):
        with patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient') as client:
            client.return_value.send_text.return_value = 'provider-message-id'
            self.assertIn('whatsapp_attempted=1', dispatch_commercial_handoff_whatsapp_alerts())
            self.assertIn('whatsapp_attempted=0', dispatch_commercial_handoff_whatsapp_alerts())
            client.return_value.send_text.assert_called_once()
            instance, target, text = client.return_value.send_text.call_args.args
            self.assertEqual(instance, self.control.instance)
            self.assertEqual(target, '5511983491206')
            self.assertIn('https://wa.me/5511999999999', text)
            self.assertNotIn(self.row.text, text)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.state, 'pending')
        self.assertEqual(self.alert.whatsapp_message_id, 'provider-message-id')

    def test_uncertain_delivery_remains_pending_and_never_retries(self):
        with patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient') as client:
            client.return_value.send_text.side_effect = TimeoutError('unknown')
            dispatch_commercial_handoff_whatsapp_alerts()
            dispatch_commercial_handoff_whatsapp_alerts()
            client.return_value.send_text.assert_called_once()
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.whatsapp_status, 'uncertain')
        self.assertEqual(self.alert.state, 'pending')

    def test_disabled_or_otp_excluded_does_not_send(self):
        self.control.handoff_notify_enabled = False
        self.control.save()
        with patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient') as client:
            dispatch_commercial_handoff_whatsapp_alerts()
            client.assert_not_called()
        self.control.handoff_notify_enabled = True
        self.control.save()
        CommercialOtpExclusion.objects.create(instance=self.control.instance, phone=self.control.handoff_notify_phone)
        with patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient') as client:
            dispatch_commercial_handoff_whatsapp_alerts()
            client.assert_not_called()

    def test_takeover_does_not_resolve_unanswered_alert(self):
        response = CommercialPanel()._post_settings(SimpleNamespace(
            data={'action': 'takeover', 'conversation': self.conv.pk}, user=self.user,
        ))
        self.assertEqual(response.status_code, 200)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.state, 'pending')

    def test_outbound_human_whatsapp_reply_resolves_alert(self):
        with patch('apps.prospecting.commercial.is_agent_outbound', return_value=False):
            receive(self.control.instance, {
                'phone': self.conv.phone, 'message_id': 'manual-device-message',
                'text': 'Olá! Vou te ajudar.', 'kind': 'text', 'from_me': True,
            })
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.state, 'resolved')
        self.assertIsNotNone(self.alert.acknowledged_at)
        self.conv.refresh_from_db()
        self.assertTrue(self.conv.paused)

    def test_panel_human_reply_resolves_only_after_confirmed_send(self):
        self.conv.owner = self.user
        self.conv.save()
        with override_settings(COMMERCIAL_HUMAN_PANEL_SEND_ENABLED=True):
            with patch('apps.prospecting.commercial_api.TenantEvolutionClient') as client:
                client.return_value.send_text.return_value = 'manual-provider-id'
                response = CommercialPanel()._send_human(SimpleNamespace(
                    data={'conversation': self.conv.pk, 'text': 'Olá, como posso ajudar?'}, user=self.user,
                ))
                self.assertEqual(response.status_code, 200)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.state, 'resolved')

    def test_external_resolution_requires_explicit_confirmation(self):
        response = CommercialPanel()._post_settings(SimpleNamespace(
            data={'action': 'resolve_handoff', 'conversation': self.conv.pk}, user=self.user,
        ))
        self.assertEqual(response.status_code, 400)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.state, 'pending')
        response = CommercialPanel()._post_settings(SimpleNamespace(
            data={'action': 'resolve_handoff', 'conversation': self.conv.pk, 'confirm_external_reply': True}, user=self.user,
        ))
        self.assertEqual(response.status_code, 200)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.state, 'resolved')

    def test_one_pending_handoff_per_conversation_until_answered(self):
        another = CommercialMessage.objects.create(
            conversation=self.conv, provider_id='second-review', text='Preciso de ajuda', state='human',
        )
        alert = alert_human(self.conv, another, 'commercial_human_review_required')
        self.assertEqual(alert.pk, self.alert.pk)
        self.assertEqual(CommercialHandoffAlert.objects.filter(state='pending').count(), 1)

    def test_pilot_allowlist_does_not_change_when_alerts_enabled(self):
        initial = list(CommercialPilotContact.objects.values_list('phone', flat=True))
        with patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient') as client:
            client.return_value.send_text.return_value = 'alert-id'
            dispatch_commercial_handoff_whatsapp_alerts()
        self.assertEqual(list(CommercialPilotContact.objects.values_list('phone', flat=True)), initial)

    def test_unapproved_lead_does_not_trigger_outbound_alert(self):
        CommercialPilotContact.objects.filter(phone=self.conv.phone).delete()
        with patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient') as client:
            dispatch_commercial_handoff_whatsapp_alerts()
            client.assert_not_called()
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.state, 'pending')
        self.assertEqual(self.alert.whatsapp_status, 'ineligible_contact')
