"""Regression coverage for isolated commercial pilot and shared OTP transport.

Authored for developer CI; not executed when assembling the delivery package.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.integrations.whatsapp.client import EvolutionError, phone_otp_transport
from .commercial import receive
from .commercial_models import (
    CommercialControl, CommercialConversation, CommercialMessage,
    CommercialPilotContact, CommercialOtpExclusion,
)
from .commercial_pilot import eligible


class SharedOtpIsolationTests(TestCase):
    def setUp(self):
        self.instance = 'vemdedelivery-comercial'
        self.phone = '5511999991234'
        CommercialControl.objects.create(pk=1, instance=self.instance, enabled=False)
        CommercialPilotContact.objects.create(phone=self.phone, active=True)

    @override_settings(COMMERCIAL_AGENT_ENABLED=True)
    def test_without_allowlist_never_sends_or_queues(self):
        from .commercial import process_message
        CommercialControl.objects.filter(pk=1).update(enabled=True)
        CommercialPilotContact.objects.filter(phone=self.phone).delete()
        with patch('apps.prospecting.commercial.TenantEvolutionClient') as client:
            row = receive(self.instance, {
                'phone': self.phone, 'message_id': 'not-allowed-001',
                'text': 'quanto custa?', 'kind': 'text', 'from_me': False,
            })
            self.assertIsNotNone(row)
            self.assertEqual(row.state, 'held')
            process_message(row.pk)
            client.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.state, 'held')

    @override_settings(
        EVOLUTION_API_URL='https://evolution.test', EVOLUTION_API_KEY='safe-test',
        EVOLUTION_INSTANCE='other-purpose', OTP_EVOLUTION_INSTANCE='vemdedelivery-comercial',
        COMMERCIAL_OTP_SHARED_ENABLED=True,
    )
    @patch('apps.integrations.whatsapp.client.EvolutionClient.request')
    def test_otp_quarantines_before_provider_post_and_blocks_automation(self, request):
        conv = CommercialConversation.objects.create(instance=self.instance, phone=self.phone)
        queued = CommercialMessage.objects.create(
            conversation=conv, provider_id='pending-lead', text='oi', state='queued'
        )
        assert eligible(self.phone, self.instance)

        def observed(method, endpoint, payload):
            self.assertEqual(method, 'POST')
            self.assertEqual(endpoint, 'message/sendText')
            self.assertTrue(CommercialOtpExclusion.objects.filter(
                instance=self.instance, phone=self.phone,
            ).exists())
            self.assertFalse(eligible(self.phone, self.instance))
            queued.refresh_from_db()
            self.assertEqual(queued.state, 'held')
            return {'key': {'id': 'provider-otp-id'}}

        request.side_effect = observed
        phone_otp_transport().send_phone_code(self.phone, 'Digite este código: 000000')
        conv.refresh_from_db()
        self.assertTrue(conv.paused)
        self.assertEqual(conv.reason, 'otp_only')
        self.assertFalse(CommercialMessage.objects.filter(text__contains='000000').exists())
        self.assertIsNone(receive(self.instance, {
            'phone': self.phone, 'message_id': 'incoming-after-otp',
            'text': 'quanto custa?', 'kind': 'text', 'from_me': False,
        }))
        self.assertFalse(CommercialMessage.objects.filter(provider_id='incoming-after-otp').exists())

    @override_settings(
        EVOLUTION_API_URL='https://evolution.test', EVOLUTION_API_KEY='safe-test',
        EVOLUTION_INSTANCE='other-purpose', OTP_EVOLUTION_INSTANCE='vemdedelivery-comercial',
        COMMERCIAL_OTP_SHARED_ENABLED=False,
    )
    @patch('apps.integrations.whatsapp.client.EvolutionClient.request')
    def test_reject_shared_otp_without_explicit_opt_in(self, request):
        with self.assertRaises(EvolutionError):
            phone_otp_transport().send_phone_code(self.phone, 'OTP')
        request.assert_not_called()

    @override_settings(
        EVOLUTION_API_URL='https://evolution.test', EVOLUTION_API_KEY='safe-test',
        EVOLUTION_INSTANCE='legacy-otp', OTP_EVOLUTION_INSTANCE='',
        COMMERCIAL_OTP_SHARED_ENABLED=False,
    )
    @patch('apps.integrations.whatsapp.client.EvolutionClient.request')
    def test_separate_legacy_otp_stays_unchanged(self, request):
        request.return_value = {'key': {'id': 'old-otp-id'}}
        phone_otp_transport().send_phone_code(self.phone, 'OTP')
        self.assertFalse(CommercialOtpExclusion.objects.exists())
        self.assertTrue(eligible(self.phone, self.instance))
        request.assert_called_once()
