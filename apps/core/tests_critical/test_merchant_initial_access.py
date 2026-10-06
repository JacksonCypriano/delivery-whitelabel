import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, override_settings

from apps.tenants.admin_site import tenant_admin_site
from .base import CriticalTestCase


@override_settings(
    TENANT_BASE_DOMAIN="vemdedelivery.com.br",
    TENANT_PUBLIC_SCHEME="https",
    DEFAULT_FROM_EMAIL="VemDeDelivery <no-reply@vemdedelivery.com.br>",
)
class MerchantInitialAccessCriticalTests(CriticalTestCase):
    platform_host = "vemdedelivery.com.br"

    def setUp(self):
        mail.outbox.clear()

    def test_superadmin_react_add_form_does_not_ask_for_password(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/api/superadmin/resources/accounts-user/new/",
            HTTP_HOST=self.platform_host,
        )
        self.assertEqual(response.status_code, 200, response.content)
        fields = {field["name"]: field for field in response.json()["fields"]}
        self.assertNotIn("password1", fields)
        self.assertNotIn("password2", fields)
        self.assertIn("tenant", fields)
        self.assertTrue(fields["email"]["required"])
        self.assertTrue(fields["tenant"]["required"])

    def _create_merchant_through_admin(self):
        self.client.force_login(self.superuser)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/superadmin/resources/accounts-user/new/",
                {
                    "username": "novo_lojista",
                    "first_name": "Maria",
                    "last_name": "Silva",
                    "email": "maria@example.com",
                    "tenant": self.tenant_a.pk,
                },
                HTTP_HOST=self.platform_host,
            )
        self.assertEqual(response.status_code, 200, response.content)
        return get_user_model().objects.get(username="novo_lojista")

    def test_creation_generates_temporary_password_and_welcome_email(self):
        user = self._create_merchant_through_admin()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_tenant_admin)
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.has_usable_password())
        self.assertIsNotNone(user.welcome_email_sent_at)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["maria@example.com"])
        self.assertIn("Bem-vindo ao VemDeDelivery", message.subject)
        self.assertIn("Login: novo_lojista", message.body)
        self.assertIn("https://alpha.vemdedelivery.com.br/", message.body)
        self.assertIn("https://alpha.vemdedelivery.com.br/painel/", message.body)

        match = re.search(r"Senha temporária: ([^\s]+)", message.body)
        self.assertIsNotNone(match)
        self.assertTrue(user.check_password(match.group(1)))

    @patch("apps.accounts.admin.generate_temporary_password", return_value="Abc123&Senha!XY")
    def test_plain_text_welcome_email_preserves_temporary_password_exactly(self, _generate):
        user = self._create_merchant_through_admin()
        self.assertIn("Senha temporária: Abc123&Senha!XY", mail.outbox[0].body)
        self.assertNotIn("Abc123&amp;Senha!XY", mail.outbox[0].body)
        self.assertTrue(user.check_password("Abc123&Senha!XY"))

    def test_first_react_login_requires_password_change_before_dashboard(self):
        user = self._create_merchant_through_admin()
        temporary_password = re.search(
            r"Senha temporária: ([^\s]+)", mail.outbox[0].body
        ).group(1)

        client = Client(HTTP_HOST="alpha.vemdedelivery.com.br")
        login_response = client.post(
            "/api/merchant/session/",
            {"username": user.username, "password": temporary_password},
        )
        self.assertEqual(login_response.status_code, 200, login_response.content)
        self.assertTrue(login_response.json()["password_change_required"])

        dashboard = client.get("/api/merchant/dashboard/")
        self.assertEqual(dashboard.status_code, 403)
        self.assertEqual(dashboard.json()["code"], "password_change_required")

    def test_password_change_form_requires_current_temporary_password(self):
        from django.contrib.auth.forms import PasswordChangeForm

        self.assertIs(tenant_admin_site.password_change_form, PasswordChangeForm)

    def test_changing_password_through_react_releases_panel(self):
        user = self._create_merchant_through_admin()
        temporary_password = re.search(
            r"Senha temporária: ([^\s]+)", mail.outbox[0].body
        ).group(1)

        client = Client(HTTP_HOST="alpha.vemdedelivery.com.br")
        login_response = client.post(
            "/api/merchant/session/",
            {"username": user.username, "password": temporary_password},
        )
        self.assertEqual(login_response.status_code, 200, login_response.content)

        change_response = client.post(
            "/api/merchant/password/",
            {
                "old_password": temporary_password,
                "new_password1": "SenhaNova!2026",
                "new_password2": "SenhaNova!2026",
            },
        )
        self.assertEqual(change_response.status_code, 200, change_response.content)

        user.refresh_from_db()
        self.assertFalse(user.must_change_password)
        self.assertTrue(user.check_password("SenhaNova!2026"))

        response = client.get("/api/merchant/dashboard/")
        self.assertEqual(response.status_code, 200, response.content)

    def test_legacy_dashboard_api_cannot_bypass_temporary_password_gate(self):
        user = self._create_merchant_through_admin()
        temporary_password = re.search(
            r"Senha temporária: ([^\s]+)", mail.outbox[0].body
        ).group(1)
        response = self.client.post(
            "/dashboard/auth/login/",
            {"username": user.username, "password": temporary_password},
            content_type="application/json",
            HTTP_HOST="alpha.vemdedelivery.com.br",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "password_change_required")
