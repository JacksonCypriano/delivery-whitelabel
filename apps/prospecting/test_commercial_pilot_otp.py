"""Regression coverage for isolated commercial pilot and shared OTP transport.

Authored for developer CI; not executed when assembling the delivery package.
"""
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase, override_settings

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


@override_settings(
    EVOLUTION_API_URL='https://evolution.test', EVOLUTION_API_KEY='safe-test',
    EVOLUTION_INSTANCE='old-otp', OTP_EVOLUTION_INSTANCE='vemdedelivery-comercial',
    COMMERCIAL_OTP_SHARED_ENABLED=True,
)
class SharedOtpCommitBoundaryTests(TransactionTestCase):
    """Real DB commits with provider mocked; never touches a WhatsApp connection."""
    def setUp(self):
        from apps.accounts.otp import create_pending
        self.phone = '11988887777'
        self.pending = create_pending({
            'first_name': 'Cliente', 'last_name': 'Teste', 'email': 'commit@example.com',
            'phone': self.phone, 'password1': 'never-shared',
        })
        from django.utils import timezone
        self.pending.email_verified_at = timezone.now()
        self.pending.save(update_fields=['email_verified_at'])
        CommercialControl.objects.create(pk=1, instance='vemdedelivery-comercial', enabled=False)

    def test_registration_exclusion_commits_before_provider_call(self):
        from django.db import connection
        from apps.accounts.otp import send_code
        observed = []
        def provider_send(number, message):
            observed.append((connection.in_atomic_block, CommercialOtpExclusion.objects.filter(
                instance='vemdedelivery-comercial', phone='5511988887777'
            ).exists()))
        with patch('apps.integrations.whatsapp.client.EvolutionClient.send_text', side_effect=provider_send):
            send_code(self.pending.pk, '192.0.2.7', 'whatsapp')
        self.assertEqual(observed, [(False, True)])

    def test_provider_failure_keeps_exclusion_and_invalidates_code(self):
        from apps.accounts.otp import send_code, OTPError
        with patch('apps.integrations.whatsapp.client.EvolutionClient.send_text', side_effect=TimeoutError()):
            with self.assertRaises(OTPError):
                send_code(self.pending.pk, '192.0.2.8', 'whatsapp')
        self.assertTrue(CommercialOtpExclusion.objects.filter(instance='vemdedelivery-comercial').exists())
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.code_hash, '')

    def test_outer_transaction_denied_before_any_send(self):
        from django.db import transaction
        from apps.accounts.otp import send_code, OTPError
        with transaction.atomic(), patch('apps.integrations.whatsapp.client.EvolutionClient.send_text') as client:
            with self.assertRaises(OTPError):
                send_code(self.pending.pk, '192.0.2.9', 'whatsapp')
            client.assert_not_called()

    def test_contact_change_exclusion_commits_before_provider_call(self):
        from django.db import connection
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from apps.customers.models import Customer
        from apps.accounts.contact_otp import save_profile, send_contact_code
        user = get_user_model().objects.create_user(
            username='contact-otp@example.com', email='contact-otp@example.com',
            password='a-valid-test-password', first_name='Cliente', email_verified=True,
            email_verified_at=timezone.now(),
        )
        Customer.objects.create(user=user, phone='11999991111', phone_verified=True)
        pending = save_profile(user.pk, {
            'first_name': 'Cliente', 'last_name': 'Teste',
            'email': 'contact-otp@example.com', 'phone': '11988887777',
        })[1][0]
        observed = []
        def provider_send(number, message):
            observed.append((connection.in_atomic_block, CommercialOtpExclusion.objects.filter(
                instance='vemdedelivery-comercial', phone='5511988887777',
            ).exists()))
        with patch('apps.integrations.whatsapp.client.EvolutionClient.send_text', side_effect=provider_send):
            send_contact_code(user.pk, pending.pk, '192.0.2.10')
        self.assertEqual(observed, [(False, True)])
