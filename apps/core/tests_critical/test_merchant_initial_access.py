import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, RequestFactory, override_settings

from apps.accounts.admin import CustomUserAdmin
from apps.tenants.admin_site import super_admin_site, tenant_admin_site
from .base import CriticalTestCase


@override_settings(
    TENANT_BASE_DOMAIN="vemdedelivery.com.br",
    TENANT_PUBLIC_SCHEME="https",
    DEFAULT_FROM_EMAIL="VemDeDelivery <no-reply@vemdedelivery.com.br>",
)
class MerchantInitialAccessCriticalTests(CriticalTestCase):
    def setUp(self):
        mail.outbox.clear()

    def test_superadmin_add_form_does_not_ask_for_password(self):
        request = RequestFactory().get("/superadmin/accounts/user/add/")
        request.user = self.superuser
        request.tenant = None
        form_class = CustomUserAdmin(get_user_model(), super_admin_site).get_form(request)
        self.assertNotIn("password1", form_class.base_fields)
        self.assertNotIn("password2", form_class.base_fields)
        self.assertIn("tenant", form_class.base_fields)
        self.assertTrue(form_class.base_fields["email"].required)
        self.assertTrue(form_class.base_fields["tenant"].required)

    def _create_merchant_through_admin(self):
        self.client.force_login(self.superuser)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/superadmin/accounts/user/add/",
                {
                    "username": "novo_lojista",
                    "first_name": "Maria",
                    "last_name": "Silva",
                    "email": "maria@example.com",
                    "tenant": self.tenant_a.pk,
                    "_save": "Salvar",
                },
                HTTP_HOST="vemdedelivery.com.br",
            )
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
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
        self.assertIn("https://alpha.vemdedelivery.com.br/admin/", message.body)

        match = re.search(r"Senha temporária: ([^\s]+)", message.body)
        self.assertIsNotNone(match)
        self.assertTrue(user.check_password(match.group(1)))

    @patch("apps.accounts.admin.generate_temporary_password", return_value="Abc123&Senha!XY")
    def test_plain_text_welcome_email_preserves_temporary_password_exactly(self, _generate):
        user = self._create_merchant_through_admin()
        self.assertIn("Senha temporária: Abc123&Senha!XY", mail.outbox[0].body)
        self.assertNotIn("Abc123&amp;Senha!XY", mail.outbox[0].body)
        self.assertTrue(user.check_password("Abc123&Senha!XY"))

    def test_first_login_is_redirected_to_password_change(self):
        user = self._create_merchant_through_admin()
        temporary_password = re.search(r"Senha temporária: ([^\s]+)", mail.outbox[0].body).group(1)

        client = Client()
        login_response = client.post(
            "/admin/login/?next=/admin/",
            {"username": user.username, "password": temporary_password, "next": "/admin/"},
            HTTP_HOST="alpha.vemdedelivery.com.br",
        )
        self.assertEqual(login_response.status_code, 302)

        response = client.get("/admin/", HTTP_HOST="alpha.vemdedelivery.com.br")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/password_change/")

    def test_password_change_form_requires_current_temporary_password(self):
        from django.contrib.auth.forms import PasswordChangeForm

        self.assertIs(tenant_admin_site.password_change_form, PasswordChangeForm)

    def test_changing_password_through_first_access_releases_panel(self):
        user = self._create_merchant_through_admin()
        temporary_password = re.search(r"Senha temporária: ([^\s]+)", mail.outbox[0].body).group(1)

        client = Client()
        login_response = client.post(
            "/admin/login/?next=/admin/",
            {"username": user.username, "password": temporary_password, "next": "/admin/"},
            HTTP_HOST="alpha.vemdedelivery.com.br",
        )
        self.assertEqual(login_response.status_code, 302)

        change_response = client.post(
            "/admin/password_change/",
            {
                "old_password": temporary_password,
                "new_password1": "SenhaNova!2026",
                "new_password2": "SenhaNova!2026",
            },
            HTTP_HOST="alpha.vemdedelivery.com.br",
        )
        self.assertEqual(change_response.status_code, 302)

        user.refresh_from_db()
        self.assertFalse(user.must_change_password)
        self.assertTrue(user.check_password("SenhaNova!2026"))

        response = client.get("/admin/", HTTP_HOST="alpha.vemdedelivery.com.br")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_api_cannot_bypass_temporary_password_gate(self):
        user = self._create_merchant_through_admin()
        temporary_password = re.search(r"Senha temporária: ([^\s]+)", mail.outbox[0].body).group(1)
        response = self.client.post(
            "/dashboard/auth/login/",
            {"username": user.username, "password": temporary_password},
            content_type="application/json",
            HTTP_HOST="alpha.vemdedelivery.com.br",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "password_change_required")
