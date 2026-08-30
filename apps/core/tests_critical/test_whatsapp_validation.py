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

    @patch("apps.integrations.whatsapp.service.requests.post")
    def test_valid_whatsapp_number_allows_registration_and_marks_verified(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"exists": True, "jid": "5511999991234@s.whatsapp.net", "number": "5511999991234"}]
        post.return_value = response
        form = CustomerRegisterForm(data=self.registration_data())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        customer = user.customer_profile
        self.assertEqual(customer.phone, "11999991234")
        self.assertTrue(customer.phone_verified)
        self.assertIsNotNone(customer.phone_verified_at)
        post.assert_called_once()

    @patch("apps.integrations.whatsapp.service.requests.post")
    def test_non_whatsapp_number_is_rejected(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"exists": False, "jid": None, "number": "5511999991234"}]
        post.return_value = response
        form = CustomerRegisterForm(data=self.registration_data())
        self.assertFalse(form.is_valid())
        self.assertIn("não foi encontrado no WhatsApp", str(form.errors["phone"]))

    @patch("apps.integrations.whatsapp.service.requests.post", side_effect=Exception("must not leak"))
    def test_unexpected_exception_is_not_swallowed(self, post):
        service = EvolutionWhatsAppService()
        with self.assertRaises(Exception):
            service.check_number("11999991234")

    @patch("apps.integrations.whatsapp.service.requests.post")
    def test_evolution_unavailable_does_not_block_registration(self, post):
        import requests
        post.side_effect = requests.Timeout("offline")
        form = CustomerRegisterForm(data=self.registration_data())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertFalse(user.customer_profile.phone_verified)
        self.assertIsNone(user.customer_profile.phone_verified_at)

    @patch("apps.integrations.whatsapp.service.requests.post")
    def test_result_is_cached(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"exists": True, "jid": "5511999991234@s.whatsapp.net", "number": "5511999991234"}]
        post.return_value = response
        service = EvolutionWhatsAppService()
        self.assertTrue(service.check_number("11999991234").exists)
        self.assertTrue(service.check_number("11999991234").exists)
        post.assert_called_once()

    @patch("apps.integrations.whatsapp.service.requests.post")
    def test_changing_phone_revalidates_and_updates_verification(self, post):
        User = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model()
        user = User.objects.create_user(username="profile@example.com", email="profile@example.com", password=self.password)
        customer = Customer.objects.create(user=user, phone="11988887777", phone_verified=True)
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"exists": True, "jid": "5511977776666@s.whatsapp.net", "number": "5511977776666"}]
        post.return_value = response
        form = CustomerProfileForm(data={"first_name": "Perfil", "last_name": "Teste", "email": "profile@example.com", "phone": "11 97777-6666"}, user=user, customer=customer)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        customer.refresh_from_db()
        self.assertEqual(customer.phone, "11977776666")
        self.assertTrue(customer.phone_verified)
