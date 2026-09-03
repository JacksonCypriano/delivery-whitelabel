from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.hashers import check_password
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.customers.models import Customer
from .models import PendingRegistration, RegistrationRateLimit, User
from .otp import OTPError, create_pending, deliver, send_code, verify_code


class RegistrationOTPTests(TestCase):
    def setUp(self):
        cache.clear()
        self.data = dict(first_name='Cliente', last_name='Teste', email='otp@example.com',
                         phone='11999991234', password1='SenhaForte!2026', password2='SenhaForte!2026')
        self.pending = create_pending(self.data)

    def send(self, channel='email', code=123456, ip='127.0.0.1'):
        with patch('apps.accounts.otp.secrets.randbelow', return_value=code), patch('apps.accounts.otp.deliver'):
            send_code(self.pending.pk, ip, channel)

    def age_send(self):
        PendingRegistration.objects.filter(pk=self.pending.pk).update(last_sent_at=timezone.now()-timedelta(seconds=61))

    def test_complete_flow_creates_only_after_both_channels(self):
        self.assertFalse(User.objects.exists())
        self.assertTrue(check_password(self.data['password1'], self.pending.password_hash))
        self.send()
        self.pending.refresh_from_db()
        self.assertNotEqual(self.pending.code_hash, '123456')
        self.assertTrue(check_password('123456', self.pending.code_hash))
        self.assertIsNone(verify_code(self.pending.pk, 'email', '123456'))
        self.assertFalse(User.objects.exists())
        self.send('whatsapp', code=234567)
        user = verify_code(self.pending.pk, 'whatsapp', '234567')
        self.assertTrue(user.email_verified)
        self.assertTrue(user.customer_profile.phone_verified)
        self.assertTrue(user.check_password(self.data['password1']))
        self.assertIsNone(user.tenant_id)
        self.assertFalse(user.is_staff)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.password_hash, '')
        with self.assertRaises(OTPError):
            verify_code(self.pending.pk, 'whatsapp', '234567')
        self.assertEqual(User.objects.count(), 1)

    def test_order_enforced(self):
        with self.assertRaises(OTPError):
            self.send('whatsapp')
        self.send()
        with self.assertRaises(OTPError):
            verify_code(self.pending.pk, 'whatsapp', '123456')
        self.assertFalse(User.objects.exists())

    def test_five_wrong_attempts_persist_and_block_correct_code(self):
        self.send()
        for _ in range(5):
            with self.assertRaises(OTPError):
                verify_code(self.pending.pk, 'email', '999999')
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.attempts, 5)
        with self.assertRaises(OTPError):
            verify_code(self.pending.pk, 'email', '123456')

    def test_resend_invalidates_old_code_and_enforces_cooldown(self):
        self.send()
        with self.assertRaises(OTPError):
            self.send()
        self.age_send()
        self.send(code=654321)
        with self.assertRaises(OTPError):
            verify_code(self.pending.pk, 'email', '123456')
        verify_code(self.pending.pk, 'email', '654321')

    def test_expiration(self):
        self.send()
        PendingRegistration.objects.filter(pk=self.pending.pk).update(code_expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(OTPError):
            verify_code(self.pending.pk, 'email', '123456')
        PendingRegistration.objects.filter(pk=self.pending.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(OTPError):
            self.send()

    def test_five_sends_per_hour_survives_new_pending_and_ip(self):
        for _ in range(5):
            self.age_send()
            self.send()
        self.pending = create_pending(self.data)
        with self.assertRaises(OTPError):
            self.send(ip='198.51.100.1')

    def test_independent_ip_and_phone_limits(self):
        for dimension in ['ip', 'phone']:
            RegistrationRateLimit.objects.all().delete()
            for i in range(5):
                data = {**self.data, 'email': f'a{i}@example.com'}
                if dimension == 'ip':
                    data['phone'] = f'1198000000{i}'
                self.pending = create_pending(data)
                self.send(ip='127.0.0.1' if dimension == 'ip' else f'198.51.100.{i}')
            self.pending = create_pending({**self.data, 'email': 'new@example.com'})
            with self.assertRaises(OTPError):
                self.send(ip='127.0.0.1' if dimension == 'ip' else '198.51.100.99')

    def test_failed_delivery_never_validates_and_consumes_send(self):
        with patch('apps.accounts.otp.deliver', side_effect=RuntimeError('private')):
            with self.assertRaises(OTPError):
                send_code(self.pending.pk, '127.0.0.1', 'email')
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.code_hash, '')
        self.assertIsNotNone(self.pending.last_sent_at)
        with self.assertRaises(OTPError):
            verify_code(self.pending.pk, 'email', '123456')

    def test_duplicate_phone_at_completion_rolls_back_user(self):
        self.send()
        verify_code(self.pending.pk, 'email', '123456')
        self.send('whatsapp')
        existing = User.objects.create_user(username='other', password='some-password')
        Customer.objects.create(user=existing, phone=self.data['phone'])
        with self.assertRaises(OTPError):
            verify_code(self.pending.pk, 'whatsapp', '123456')
        self.assertFalse(User.objects.filter(email=self.data['email']).exists())

    def test_email_delivery(self):
        deliver('email', self.pending, '012345')
        self.assertEqual(mail.outbox[0].to, [self.data['email']])
        self.assertIn('012345', mail.outbox[0].body)

    @override_settings(EVOLUTION_API_URL='https://evolution.test', EVOLUTION_API_KEY='test', EVOLUTION_INSTANCE='delivery', EVOLUTION_API_TIMEOUT=4)
    @patch('apps.integrations.whatsapp.client.EvolutionClient.request')
    def test_whatsapp_delivery(self, post):
        post.return_value = {'key': {'id': 'message-id'}}
        deliver('whatsapp', self.pending, '012345')
        args = post.call_args
        self.assertEqual(args.args[:2], ('POST', 'message/sendText'))
        self.assertEqual(args.args[2]['number'], '5511999991234')
        self.assertIn('*012345*', args.args[2]['text'])
        post.return_value = {}
        with self.assertRaises(OTPError):
            deliver('whatsapp', self.pending, '012345')

    @override_settings(EVOLUTION_API_URL='', EVOLUTION_API_KEY='', EVOLUTION_INSTANCE='')
    def test_missing_whatsapp_config_fails_closed(self):
        with self.assertRaises(OTPError):
            deliver('whatsapp', self.pending, '012345')

    @patch('apps.accounts.otp.deliver')
    @patch('apps.accounts.otp.secrets.randbelow', return_value=123456)
    def test_browser_flow_session_binding_and_redirect(self, random, deliver_mock):
        result = self.client.post('/conta/criar-conta/', {**self.data, 'next': '/conta/'})
        self.assertRedirects(result, '/conta/criar-conta/validar/')
        self.assertFalse(User.objects.exists())
        self.assertNotIn('_auth_user_id', self.client.session)
        stranger = Client()
        result = stranger.post('/conta/criar-conta/validar/', {'action': 'verify', 'channel': 'email', 'code': '123456'})
        self.assertEqual(result.url, '/conta/criar-conta/')
        self.client.post('/conta/criar-conta/validar/', {'action': 'verify', 'channel': 'email', 'code': '123456'})
        self.assertFalse(User.objects.exists())
        result = self.client.post('/conta/criar-conta/validar/', {'action': 'verify', 'channel': 'whatsapp', 'code': '123456'})
        self.assertEqual(result.url, '/conta/')
        self.assertIn('_auth_user_id', self.client.session)
        self.assertNotIn('pending_registration', self.client.session)

    def test_csrf_enforced(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/conta/criar-conta/validar/', {'action': 'send'}).status_code, 403)

    def test_profile_changes_preserve_contacts_until_confirmation(self):
        from .forms import CustomerProfileForm
        user = User.objects.create_user(username='old@example.com', email='old@example.com', email_verified=True, email_verified_at=timezone.now())
        customer = Customer.objects.create(user=user, phone='11988887777', phone_verified=True, phone_verified_at=timezone.now())
        form = CustomerProfileForm(data={k: self.data[k] for k in ['first_name', 'last_name', 'email', 'phone']}, user=user, customer=customer, skip_whatsapp_validation=True)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()
        customer.refresh_from_db()
        self.assertEqual(user.email, 'old@example.com')
        self.assertEqual(user.username, 'old@example.com')
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)
        self.assertEqual(customer.phone, '11988887777')
        self.assertTrue(customer.phone_verified)
        self.assertIsNotNone(customer.phone_verified_at)
        self.assertEqual(len(form.pending_changes), 2)


# Run these against PostgreSQL: SQLite does not implement select_for_update.
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature


@skipUnlessDBFeature('has_select_for_update')
class RegistrationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.pending = create_pending(dict(first_name='Race', last_name='Test', email='race@example.com', phone='11977776666', password1='SenhaForte!2026'))

    def race(self, operation):
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    operation()
                    return 'ok'
                except OTPError:
                    return 'blocked'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda _: worker(), range(2)))

    @patch('apps.accounts.otp.deliver')
    def test_parallel_sends_deliver_once(self, delivery):
        results = self.race(lambda: send_code(self.pending.pk, '127.0.0.1', 'email'))
        self.assertCountEqual(results, ['ok', 'blocked'])
        self.assertEqual(delivery.call_count, 1)

    @patch('apps.accounts.otp.deliver')
    @patch('apps.accounts.otp.secrets.randbelow', return_value=123456)
    def test_parallel_completion_creates_one_account(self, random, delivery):
        send_code(self.pending.pk, '127.0.0.1', 'email')
        verify_code(self.pending.pk, 'email', '123456')
        send_code(self.pending.pk, '127.0.0.1', 'whatsapp')
        results = self.race(lambda: verify_code(self.pending.pk, 'whatsapp', '123456'))
        self.assertCountEqual(results, ['ok', 'blocked'])
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)
