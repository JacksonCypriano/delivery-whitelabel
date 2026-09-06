import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import RequestFactory, override_settings

from apps.tenants.admin import TenantAdmin
from apps.tenants.admin_site import super_admin_site
from apps.tenants.models import Tenant

from .base import CriticalTestCase


@override_settings(
    TENANT_BASE_DOMAIN="vemdedelivery.com.br",
    TENANT_PUBLIC_SCHEME="https",
    DEFAULT_FROM_EMAIL="VemDeDelivery <no-reply@vemdedelivery.com.br>",
    BILLING_ENABLED=False,
)
class StoreMerchantOnboardingCriticalTests(CriticalTestCase):
    def setUp(self):
        mail.outbox.clear()
        self.client.force_login(self.superuser)

    def _payload(self, **overrides):
        data = {
            "name": "Burger Central",
            "slug": "burger-central",
            "whatsapp_number": "5511999997788",
            "merchant_name": "João da Silva",
            "merchant_email": "joao@burgercentral.com.br",
            "sale_mode": "whatsapp",
            "fulfillment_mode": "delivery_and_pickup",
            "is_active": "on",
            "_save": "Salvar",
        }
        data.update(overrides)
        return data

    def _create_store(self, **overrides):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/superadmin/tenants/tenant/add/",
                self._payload(**overrides),
                HTTP_HOST="vemdedelivery.com.br",
            )
        return response

    def test_store_add_form_contains_required_merchant_access_fields(self):
        request = RequestFactory().get("/superadmin/tenants/tenant/add/")
        request.user = self.superuser
        request.tenant = None
        form_class = TenantAdmin(Tenant, super_admin_site).get_form(request, obj=None)

        self.assertIn("merchant_name", form_class.base_fields)
        self.assertIn("merchant_email", form_class.base_fields)
        self.assertTrue(form_class.base_fields["merchant_name"].required)
        self.assertTrue(form_class.base_fields["merchant_email"].required)

    def test_creating_store_creates_merchant_and_sends_welcome_email(self):
        response = self._create_store()
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))

        tenant = Tenant.objects.get(slug="burger-central")
        User = get_user_model()
        user = User.objects.get(username="joao@burgercentral.com.br")

        self.assertEqual(user.email, "joao@burgercentral.com.br")
        self.assertEqual(user.first_name, "João")
        self.assertEqual(user.last_name, "da Silva")
        self.assertEqual(user.tenant, tenant)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_tenant_admin)
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.has_usable_password())
        self.assertIsNotNone(user.welcome_email_sent_at)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["joao@burgercentral.com.br"])
        self.assertIn("Login: joao@burgercentral.com.br", message.body)
        self.assertIn("https://burger-central.vemdedelivery.com.br/", message.body)
        self.assertIn("https://burger-central.vemdedelivery.com.br/admin/", message.body)

        password_match = re.search(r"Senha temporária: ([^\s]+)", message.body)
        self.assertIsNotNone(password_match)
        self.assertTrue(user.check_password(password_match.group(1)))

    def test_duplicate_merchant_email_prevents_store_creation(self):
        User = get_user_model()
        User.objects.create_user(
            username="existing@example.com",
            email="existing@example.com",
            password=self.password,
        )

        response = self._create_store(merchant_email="EXISTING@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Tenant.objects.filter(slug="burger-central").exists())
        self.assertContains(response, "Já existe uma conta cadastrada com este e-mail")
        self.assertEqual(len(mail.outbox), 0)

    def test_editing_store_does_not_generate_new_access_or_email(self):
        response = self._create_store()
        self.assertEqual(response.status_code, 302)
        tenant = Tenant.objects.get(slug="burger-central")
        user_id = tenant.users.get(is_tenant_admin=True).pk
        mail.outbox.clear()

        edit_payload = {
            "name": "Burger Central Atualizada",
            "slug": "burger-central",
            "whatsapp_number": "5511999997788",
            "sale_mode": "whatsapp",
            "fulfillment_mode": "delivery_and_pickup",
            "is_active": "on",
            "_save": "Salvar",
        }
        with self.captureOnCommitCallbacks(execute=True):
            edit_response = self.client.post(
                f"/superadmin/tenants/tenant/{tenant.pk}/change/",
                edit_payload,
                HTTP_HOST="vemdedelivery.com.br",
            )

        self.assertEqual(edit_response.status_code, 302, getattr(edit_response, "context", None))
        tenant.refresh_from_db()
        self.assertEqual(tenant.name, "Burger Central Atualizada")
        self.assertEqual(tenant.users.filter(is_tenant_admin=True).count(), 1)
        self.assertEqual(tenant.users.get(is_tenant_admin=True).pk, user_id)
        self.assertEqual(len(mail.outbox), 0)

    def test_superadmin_sidebar_starts_with_store_and_access_group(self):
        navigation = settings.UNFOLD_SUPER["SIDEBAR"]["navigation"]
        self.assertEqual(str(navigation[0]["title"]), "Lojas e acessos")
        self.assertTrue(navigation[0]["collapsible"])
        self.assertEqual(str(navigation[0]["items"][0]["title"]), "Cadastrar loja + usuário")
        self.assertEqual(
            str(navigation[0]["items"][0]["link"]),
            "/superadmin/tenants/tenant/add/",
        )

        # Força a resolução de todos os links do menu para detectar nomes de URL inválidos.
        for group in navigation:
            for item in group["items"]:
                self.assertTrue(str(item["link"]).startswith("/superadmin/"))
