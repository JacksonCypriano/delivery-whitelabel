from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import Mock, patch

from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from .contact_otp import (
    cancel_contact_change, deliver_contact_code, pending_changes,
    save_profile, send_contact_code, verify_contact_code,
)
from .models import PendingContactChange, RegistrationRateLimit, User
from .otp import OTPError, create_pending, send_code


@override_settings(EVOLUTION_WHATSAPP_VALIDATION_ENABLED=False)
class ContactOTPTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = "SenhaForte!2026"
        self.user = User.objects.create_user(
            username="old@example.com", email="old@example.com", first_name="Cliente", last_name="Teste",
            password=self.password, email_verified=True, email_verified_at=timezone.now(),
        )
        self.customer = Customer.objects.create(user=self.user, phone="11999991111", phone_verified=True, phone_verified_at=timezone.now())
        self.data = dict(first_name="Novo nome", last_name="Teste", email="new@example.com", phone=self.customer.phone)
        self.client.force_login(self.user)

    def stage(self, **kwargs):
        return save_profile(self.user.pk, {**self.data, **kwargs})[1]

    def send(self, pending, code=123456, ip="127.0.0.1"):
        with patch("apps.accounts.contact_otp.secrets.randbelow", return_value=code), patch("apps.accounts.contact_otp.deliver_contact_code"):
            send_contact_code(self.user.pk, pending.pk, ip)

    def age_send(self, pending):
        PendingContactChange.objects.filter(pk=pending.pk).update(last_sent_at=timezone.now()-timedelta(seconds=61))

    def url(self, pending):
        return reverse("customer_accounts:verify-contact", kwargs={"change_id": pending.pk})

    def assert_old_contacts(self):
        self.user.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")
        self.assertEqual(self.user.username, "old@example.com")
        self.assertTrue(self.user.email_verified)
        self.assertEqual(self.customer.phone, "11999991111")
        self.assertTrue(self.customer.phone_verified)

    def test_staging_keeps_current_contacts_and_verification(self):
        before = (self.user.email_verified_at, self.customer.phone_verified_at)
        pending = self.stage(phone="11988882222")
        self.assertEqual(len(pending), 2)
        self.assert_old_contacts()
        self.assertEqual(self.user.first_name, "Novo nome")
        self.assertEqual((self.user.email_verified_at, self.customer.phone_verified_at), before)
        self.assertEqual(User.objects.count(), 1)

    def test_name_only_change_does_not_create_pending(self):
        self.assertEqual(self.stage(email=self.user.email), [])
        self.assert_old_contacts()
        self.assertEqual(self.user.first_name, "Novo nome")

    def test_email_confirmation_changes_login_and_keeps_password(self):
        pending = self.stage()[0]
        self.send(pending)
        self.assertIsNotNone(authenticate(username="old@example.com", password=self.password))
        verify_contact_code(self.user.pk, pending.pk, "123456")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertEqual(self.user.username, "new@example.com")
        self.assertTrue(self.user.email_verified)
        self.assertIsNone(authenticate(username="old@example.com", password=self.password))
        self.assertEqual(authenticate(username="new@example.com", password=self.password).pk, self.user.pk)
        pending.refresh_from_db()
        self.assertEqual(pending.code_hash, "")
        self.assertIsNotNone(pending.completed_at)
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "123456")

    def test_phone_confirmation_does_not_change_email(self):
        pending = self.stage(email=self.user.email, phone="11988882222")[0]
        self.send(pending)
        verify_contact_code(self.user.pk, pending.pk, "123456")
        self.customer.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.customer.phone, "11988882222")
        self.assertTrue(self.customer.phone_verified)
        self.assertEqual(self.user.email, "old@example.com")

    def test_each_of_two_contacts_requires_its_own_otp(self):
        email, phone = self.stage(phone="11988882222")
        self.send(email, code=123456)
        self.send(phone, code=654321)
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, phone.pk, "123456")
        verify_contact_code(self.user.pk, email.pk, "123456")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.phone, "11999991111")
        verify_contact_code(self.user.pk, phone.pk, "654321")
        self.assertFalse(pending_changes(self.user).exists())

    def test_hash_and_leading_zero(self):
        pending = self.stage()[0]
        self.send(pending, code=123)
        pending.refresh_from_db()
        self.assertNotEqual(pending.code_hash, "000123")
        self.assertTrue(check_password("000123", pending.code_hash))
        verify_contact_code(self.user.pk, pending.pk, "000123")

    def test_wrong_attempts_commit_and_fifth_blocks_correct_code(self):
        pending = self.stage()[0]
        self.send(pending)
        for _ in range(5):
            with self.assertRaises(OTPError):
                verify_contact_code(self.user.pk, pending.pk, "000000")
        pending.refresh_from_db()
        self.assertEqual(pending.attempts, 5)
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "123456")
        self.assert_old_contacts()

    def test_resubmitting_same_destination_does_not_reset_attempts_or_expiry(self):
        pending = self.stage()[0]
        self.send(pending)
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "wrong")
        repeated = self.stage()[0]
        self.assertEqual(repeated.pk, pending.pk)
        self.assertEqual(repeated.attempts, 1)
        self.assertEqual(repeated.expires_at, pending.expires_at)

    def test_replacement_invalidates_old_url_and_retains_cooldown(self):
        pending = self.stage()[0]
        self.send(pending)
        replacement = self.stage(email="different@example.com")[0]
        self.assertNotEqual(replacement.pk, pending.pk)
        self.assertEqual(self.client.get(self.url(pending)).status_code, 404)
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "123456")
        with self.assertRaises(OTPError):
            self.send(replacement)
        self.assert_old_contacts()

    def test_cancel_preserves_contacts_and_invalidates_code(self):
        pending = self.stage()[0]
        self.send(pending)
        cancel_contact_change(self.user.pk, pending.pk)
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "123456")
        replacement = self.stage()[0]
        with self.assertRaises(OTPError):
            self.send(replacement)
        self.assert_old_contacts()

    def test_resend_cooldown_and_old_code_invalidation(self):
        pending = self.stage()[0]
        self.send(pending)
        with self.assertRaises(OTPError):
            self.send(pending)
        self.age_send(pending)
        self.send(pending, code=654321)
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "123456")
        verify_contact_code(self.user.pk, pending.pk, "654321")

    def test_expired_code_and_pending_do_not_change_contacts(self):
        pending = self.stage()[0]
        self.send(pending)
        PendingContactChange.objects.filter(pk=pending.pk).update(code_expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "123456")
        PendingContactChange.objects.filter(pk=pending.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(OTPError):
            self.send(pending)
        self.assert_old_contacts()

    def test_failed_delivery_consumes_cooldown_and_does_not_change_contacts(self):
        pending = self.stage()[0]
        with patch("apps.accounts.contact_otp.deliver_contact_code", side_effect=RuntimeError("secret-provider-error")):
            with self.assertRaises(OTPError) as caught:
                send_contact_code(self.user.pk, pending.pk, "127.0.0.1")
        self.assertNotIn("secret-provider-error", str(caught.exception))
        pending.refresh_from_db()
        self.assertEqual(pending.code_hash, "")
        self.assertIsNotNone(pending.last_sent_at)
        with self.assertRaises(OTPError):
            self.send(pending)
        self.assert_old_contacts()

    def test_limit_of_five_sends_survives_changed_destination_and_ip(self):
        for index in range(5):
            pending = self.stage(email=f"next{index}@example.com")[0]
            self.age_send(pending)
            self.send(pending, ip=f"192.0.2.{index}")
        pending = self.stage(email="sixth@example.com")[0]
        self.age_send(pending)
        with self.assertRaises(OTPError):
            self.send(pending, ip="192.0.2.99")

    def test_destination_limit_is_shared_with_registration(self):
        for _ in range(5):
            registration = create_pending(dict(first_name="Other", last_name="Client", email="new@example.com", phone="11912345678", password1=self.password))
            with patch("apps.accounts.otp.deliver"):
                send_code(registration.pk, "192.0.2.1", "email")
        pending = self.stage()[0]
        with self.assertRaises(OTPError):
            self.send(pending, ip="198.51.100.1")

    def test_hourly_limit_expires(self):
        pending = self.stage()[0]
        for _ in range(5):
            self.age_send(pending)
            self.send(pending)
        for bucket in RegistrationRateLimit.objects.all():
            bucket.events = [timezone.now().timestamp() - 3601] * 5
            bucket.save()
        self.age_send(pending)
        self.send(pending)

    def test_duplicate_email_at_confirmation_preserves_original(self):
        pending = self.stage()[0]
        self.send(pending)
        User.objects.create_user(username="new@example.com", email="new@example.com", password=self.password)
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "123456")
        self.assert_old_contacts()
        pending.refresh_from_db()
        self.assertIsNotNone(pending.cancelled_at)

    def test_duplicate_phone_at_confirmation_preserves_original(self):
        pending = self.stage(email=self.user.email, phone="11988882222")[0]
        self.send(pending)
        other = User.objects.create_user(username="other@example.com", password=self.password)
        Customer.objects.create(user=other, phone=pending.destination)
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "123456")
        self.assert_old_contacts()

    def test_stale_request_cannot_overwrite_external_change(self):
        pending = self.stage()[0]
        self.send(pending)
        User.objects.filter(pk=self.user.pk).update(email="external@example.com", username="external@example.com")
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "123456")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "external@example.com")

    def test_other_customer_cannot_read_send_verify_or_cancel(self):
        pending = self.stage()[0]
        self.send(pending)
        other = User.objects.create_user(username="other@example.com", password=self.password)
        Customer.objects.create(user=other, phone="11922223333")
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url(pending)).status_code, 404)
        for action in ["send", "verify", "cancel"]:
            self.assertEqual(self.client.post(self.url(pending), {"action": action, "code": "123456"}).status_code, 404)
        for operation in [lambda: send_contact_code(other.pk, pending.pk, "127.0.0.1"),
                          lambda: verify_contact_code(other.pk, pending.pk, "123456"),
                          lambda: cancel_contact_change(other.pk, pending.pk)]:
            with self.assertRaises(OTPError):
                operation()
        self.assert_old_contacts()

    def test_csrf_and_login_required(self):
        pending = self.stage()[0]
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for action in ["send", "verify", "cancel"]:
            self.assertEqual(client.post(self.url(pending), {"action": action}).status_code, 403)
        client.logout()
        self.assertEqual(client.get(self.url(pending)).status_code, 302)

    @patch("apps.accounts.contact_otp.deliver_contact_code")
    def test_get_never_sends(self, delivery):
        pending = self.stage()[0]
        self.assertContains(self.client.get(self.url(pending)), "Confirmar e atualizar")
        self.assertContains(self.client.get("/conta/dados/"), "Confirmação de contato pendente")
        delivery.assert_not_called()

    @patch("apps.accounts.contact_otp.deliver_contact_code")
    @patch("apps.accounts.contact_otp.secrets.randbelow", return_value=123456)
    def test_browser_two_contact_flow_preserves_session(self, random, delivery):
        response = self.client.post("/conta/dados/", {**self.data, "phone": "11988882222"})
        email, phone = list(pending_changes(self.user))
        self.assertEqual(response.url, self.url(email))
        self.assertEqual(delivery.call_count, 1)
        self.assert_old_contacts()
        response = self.client.post(self.url(email), {"action": "verify", "code": "123456"})
        self.assertEqual(response.url, self.url(phone))
        self.assertEqual(delivery.call_count, 2)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.phone, "11999991111")
        response = self.client.post(self.url(phone), {"action": "verify", "code": "123456"})
        self.assertEqual(response.url, "/conta/dados/")
        self.assertContains(self.client.get(response.url), "new@example.com")
        self.assertFalse(pending_changes(self.user).exists())
        self.client.logout()
        response = self.client.post("/conta/entrar/", {"email": "new@example.com", "password": self.password})
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_delivery_email_uses_new_destination_and_change_copy(self):
        pending = self.stage()[0]
        deliver_contact_code(pending, self.user, "123456")
        self.assertEqual(mail.outbox[0].to, ["new@example.com"])
        self.assertIn("novo e-mail", mail.outbox[0].subject)
        self.assertIn("\n\n    123456\n\n", mail.outbox[0].body)
        self.assertNotIn("continuar seu cadastro", mail.outbox[0].body)

    @override_settings(EVOLUTION_API_URL="https://evolution.test", EVOLUTION_API_KEY="test-key", EVOLUTION_INSTANCE="delivery", EVOLUTION_API_TIMEOUT=4)
    @patch("apps.integrations.whatsapp.client.EvolutionClient.request")
    def test_delivery_whatsapp_uses_new_number_and_rejects_bad_response(self, post):
        pending = self.stage(email=self.user.email, phone="11988882222")[0]
        post.return_value = {"key": {"id": "message-id"}}
        deliver_contact_code(pending, self.user, "123456")
        self.assertEqual(post.call_args.args[2]["number"], "5511988882222")
        self.assertIn("\n\n*123456*\n\n", post.call_args.args[2]["text"])
        post.return_value = {}
        with self.assertRaises(OTPError):
            deliver_contact_code(pending, self.user, "123456")

    def test_cleanup_removes_expired_not_active_or_recent_cancelled(self):
        pending = self.stage()[0]
        cancel_contact_change(self.user.pk, pending.pk)
        call_command("cleanup_registrations", verbosity=0)
        self.assertTrue(PendingContactChange.objects.filter(pk=pending.pk).exists())
        PendingContactChange.objects.filter(pk=pending.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        call_command("cleanup_registrations", verbosity=0)
        self.assertFalse(PendingContactChange.objects.filter(pk=pending.pk).exists())


@skipUnlessDBFeature("has_select_for_update")
class ContactOTPConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="old@example.com", email="old@example.com", password="SenhaForte!2026")
        Customer.objects.create(user=self.user, phone="11999991111")
        self.data = dict(first_name="Cliente", last_name="Teste", email="new@example.com", phone="11999991111")
        self.pending = save_profile(self.user.pk, self.data)[1][0]

    def race(self, operations):
        barrier = Barrier(len(operations))
        def worker(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    operation()
                    return "ok"
                except OTPError:
                    return "blocked"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            return list(pool.map(worker, operations))

    @patch("apps.accounts.contact_otp.deliver_contact_code")
    def test_simultaneous_sends_deliver_once(self, delivery):
        operation = lambda: send_contact_code(self.user.pk, self.pending.pk, "127.0.0.1")
        self.assertCountEqual(self.race([operation, operation]), ["ok", "blocked"])
        self.assertEqual(delivery.call_count, 1)

    @patch("apps.accounts.contact_otp.deliver_contact_code")
    @patch("apps.accounts.contact_otp.secrets.randbelow", return_value=123456)
    def test_simultaneous_verification_consumes_once(self, random, delivery):
        send_contact_code(self.user.pk, self.pending.pk, "127.0.0.1")
        operation = lambda: verify_contact_code(self.user.pk, self.pending.pk, "123456")
        self.assertCountEqual(self.race([operation, operation]), ["ok", "blocked"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")

    @patch("apps.accounts.contact_otp.deliver_contact_code")
    @patch("apps.accounts.contact_otp.secrets.randbelow", return_value=123456)
    def test_two_accounts_cannot_claim_same_email(self, random, delivery):
        other = User.objects.create_user(username="other@example.com", email="other@example.com", password="SenhaForte!2026")
        Customer.objects.create(user=other, phone="11922223333")
        other_pending = save_profile(other.pk, {**self.data, "phone": "11922223333"})[1][0]
        send_contact_code(self.user.pk, self.pending.pk, "127.0.0.1")
        send_contact_code(other.pk, other_pending.pk, "127.0.0.2")
        results = self.race([
            lambda: verify_contact_code(self.user.pk, self.pending.pk, "123456"),
            lambda: verify_contact_code(other.pk, other_pending.pk, "123456"),
        ])
        self.assertCountEqual(results, ["ok", "blocked"])
        self.assertEqual(User.objects.filter(email="new@example.com").count(), 1)

    @patch("apps.accounts.contact_otp.deliver_contact_code")
    @patch("apps.accounts.contact_otp.secrets.randbelow", return_value=123456)
    def test_cancel_racing_verify_has_consistent_outcome(self, random, delivery):
        send_contact_code(self.user.pk, self.pending.pk, "127.0.0.1")
        results = self.race([
            lambda: verify_contact_code(self.user.pk, self.pending.pk, "123456"),
            lambda: cancel_contact_change(self.user.pk, self.pending.pk),
        ])
        self.assertCountEqual(results, ["ok", "blocked"])
        self.user.refresh_from_db()
        self.pending.refresh_from_db()
        if self.pending.completed_at:
            self.assertEqual(self.user.email, "new@example.com")
            self.assertIsNone(self.pending.cancelled_at)
        else:
            self.assertEqual(self.user.email, "old@example.com")
            self.assertIsNotNone(self.pending.cancelled_at)
