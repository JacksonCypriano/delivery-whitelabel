from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import override_settings

from apps.accounts.forms import CustomerProfileForm, CustomerRegisterForm
from apps.customers.models import Customer
from apps.integrations.whatsapp.service import EvolutionWhatsAppService, normalize_br_phone
from .base import CriticalTestCase


EVOLUTION_SETTINGS = dict(
    EVOLUTION_WHATSAPP_VALIDATION_ENABLED=True,
    EVOLUTION_API_URL="http://evolution.test",
    EVOLUTION_API_KEY="secret-test-key",
    EVOLUTION_INSTANCE="vemdedelivery",
    EVOLUTION_API_TIMEOUT=2,
    EVOLUTION_CHECK_CACHE_SECONDS=3600,
)


@override_settings(**EVOLUTION_SETTINGS)
class WhatsAppValidationTests(CriticalTestCase):
    def setUp(self):
        cache.clear()

    def registration_data(self, phone="(11) 99999-1234"):
        return {"first_name": "Cliente", "last_name": "Teste", "email": "cliente.evolution@example.com", "phone": phone, "password1": self.password, "password2": self.password}

    def test_normalizes_brazilian_phone(self):
        self.assertEqual(normalize_br_phone("+55 (11) 99999-1234"), "5511999991234")
        self.assertEqual(normalize_br_phone("11 99999-1234"), "5511999991234")

    @patch("apps.integrations.whatsapp.service.EvolutionClient.request")
    def test_valid_whatsapp_number_creates_pending_without_proving_ownership(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"exists": True, "jid": "5511999991234@s.whatsapp.net", "number": "5511999991234"}]
        post.return_value = response.json()
        form = CustomerRegisterForm(data=self.registration_data())
        self.assertTrue(form.is_valid(), form.errors)
        pending = form.save()
        self.assertEqual(pending.phone, "11999991234")
        self.assertIsNone(pending.email_verified_at)
        self.assertFalse(Customer.objects.filter(phone=pending.phone).exists())
        post.assert_called_once()

    @patch("apps.integrations.whatsapp.service.EvolutionClient.request")
    def test_non_whatsapp_number_is_rejected(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"exists": False, "jid": None, "number": "5511999991234"}]
        post.return_value = response.json()
        form = CustomerRegisterForm(data=self.registration_data())
        self.assertFalse(form.is_valid())
        self.assertIn("não foi encontrado no WhatsApp", str(form.errors["phone"]))

    @patch("apps.integrations.whatsapp.service.EvolutionClient.request", side_effect=Exception("must not leak"))
    def test_unexpected_exception_is_not_swallowed(self, post):
        service = EvolutionWhatsAppService()
        with self.assertRaises(Exception):
            service.check_number("11999991234")

    @patch("apps.integrations.whatsapp.service.EvolutionClient.request")
    def test_evolution_unavailable_does_not_block_registration(self, post):
        from apps.integrations.whatsapp.client import EvolutionError
        post.side_effect = EvolutionError("unavailable")
        form = CustomerRegisterForm(data=self.registration_data())
        self.assertTrue(form.is_valid(), form.errors)
        pending = form.save()
        self.assertIsNone(pending.email_verified_at)
        self.assertFalse(Customer.objects.filter(phone=pending.phone).exists())

    @patch("apps.integrations.whatsapp.service.EvolutionClient.request")
    def test_result_is_cached(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"exists": True, "jid": "5511999991234@s.whatsapp.net", "number": "5511999991234"}]
        post.return_value = response.json()
        service = EvolutionWhatsAppService()
        self.assertTrue(service.check_number("11999991234").exists)
        self.assertTrue(service.check_number("11999991234").exists)
        post.assert_called_once()

    @patch("apps.integrations.whatsapp.service.EvolutionClient.request")
    def test_changing_phone_stages_change_without_replacing_verified_contact(self, post):
        User = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model()
        user = User.objects.create_user(username="profile@example.com", email="profile@example.com", password=self.password)
        customer = Customer.objects.create(user=user, phone="11988887777", phone_verified=True)
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"exists": True, "jid": "5511977776666@s.whatsapp.net", "number": "5511977776666"}]
        post.return_value = response.json()
        form = CustomerProfileForm(data={"first_name": "Perfil", "last_name": "Teste", "email": "profile@example.com", "phone": "11 97777-6666"}, user=user, customer=customer)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        customer.refresh_from_db()
        self.assertEqual(customer.phone, "11988887777")
        self.assertTrue(customer.phone_verified)
        self.assertEqual(form.pending_changes[0].destination, "11977776666")

    @patch("apps.integrations.whatsapp.service.EvolutionClient.request")
    def test_profile_rate_limit_blocks_sixth_distinct_phone_without_calling_evolution(self, post):
        User = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model()
        user = User.objects.create_user(username="limited@example.com", email="limited@example.com", password=self.password)
        Customer.objects.create(user=user, phone="11911111111", phone_verified=True)
        self.client.force_login(user)

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = lambda: [{"exists": True, "jid": "test@s.whatsapp.net", "number": "5511999999999"}]
        post.return_value = response.json()

        for index in range(5):
            phone = f"1198000000{index}"
            result = self.client.post("/conta/dados/", {"first_name": "Perfil", "last_name": "Teste", "email": "limited@example.com", "phone": phone}, HTTP_HOST="lvh.me")
            self.assertEqual(result.status_code, 302)

        calls_before_limit = post.call_count
        result = self.client.post("/conta/dados/", {"first_name": "Perfil", "last_name": "Teste", "email": "limited@example.com", "phone": "11980000005"}, HTTP_HOST="lvh.me")
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Muitas tentativas de alteração do WhatsApp")
        self.assertEqual(post.call_count, calls_before_limit)

    @patch("apps.integrations.whatsapp.service.EvolutionClient.request")
    def test_profile_distinct_limit_cannot_be_bypassed_by_retrying_blocked_phone(self, post):
        User = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model()
        user = User.objects.create_user(username="retry-limit@example.com", email="retry-limit@example.com", password=self.password)
        Customer.objects.create(user=user, phone="11911112222", phone_verified=True)
        self.client.force_login(user)

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"exists": True, "jid": "test@s.whatsapp.net", "number": "5511980000000"}]
        post.return_value = response.json()

        for index in range(5):
            result = self.client.post("/conta/dados/", {"first_name": "Perfil", "last_name": "Teste", "email": "retry-limit@example.com", "phone": f"1198100000{index}"}, HTTP_HOST="lvh.me")
            self.assertEqual(result.status_code, 302)

        blocked_phone = "11981000005"
        calls_before_limit = post.call_count

        first = self.client.post("/conta/dados/", {"first_name": "Perfil", "last_name": "Teste", "email": "retry-limit@example.com", "phone": blocked_phone}, HTTP_HOST="lvh.me")
        second = self.client.post("/conta/dados/", {"first_name": "Perfil", "last_name": "Teste", "email": "retry-limit@example.com", "phone": blocked_phone}, HTTP_HOST="lvh.me")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertContains(first, "Muitas tentativas de alteração do WhatsApp")
        self.assertContains(second, "Muitas tentativas de alteração do WhatsApp")
        self.assertEqual(post.call_count, calls_before_limit)
