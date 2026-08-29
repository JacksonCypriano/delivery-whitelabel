import re
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings

from apps.customers.models import Customer

from .base import CriticalTestCase


@override_settings(
    CUSTOMER_PORTAL_URL="https://vemdedelivery.com.br",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="VemDeDelivery <no-reply@vemdedelivery.com.br>",
)
class CustomerPasswordResetCriticalTests(CriticalTestCase):
    customer_email = "cliente@example.com"
    old_password = "SenhaAntiga!2026"
    new_password = "SenhaNova!2026"

    def setUp(self):
        User = get_user_model()
        self.customer_user = User.objects.create_user(
            username=self.customer_email,
            email=self.customer_email,
            first_name="Cliente",
            password=self.old_password,
            tenant=None,
            is_tenant_admin=False,
            is_staff=False,
        )
        Customer.objects.create(user=self.customer_user, phone="11988887777")
        mail.outbox.clear()

    def _request_reset(self, email=None, host=None):
        return self.client.post(
            "/conta/recuperar-senha/",
            {"email": email or self.customer_email},
            HTTP_HOST=host or self.host(self.tenant_a),
        )

    def _reset_path_from_email(self):
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"https://vemdedelivery\.com\.br(/conta/redefinir-senha/[^\s]+)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        return match.group(1)

    def _open_real_token(self):
        path = self._reset_path_from_email()
        response = self.client.get(path, HTTP_HOST="vemdedelivery.com.br")
        self.assertEqual(response.status_code, 302)
        redirected = urlsplit(response["Location"]).path
        self.assertIn("/set-password/", redirected)
        return path, redirected

    def test_existing_customer_receives_global_reset_link(self):
        response = self._request_reset(host=self.host(self.tenant_a))
        self.assertRedirects(
            response,
            "/conta/recuperar-senha/enviado/",
            fetch_redirect_response=False,
        )
        path = self._reset_path_from_email()
        self.assertTrue(path.startswith("/conta/redefinir-senha/"))
        self.assertNotIn(self.host(self.tenant_a), mail.outbox[0].body)

    def test_unknown_email_has_same_response_and_sends_nothing(self):
        response = self._request_reset("naoexiste@example.com")
        self.assertRedirects(
            response,
            "/conta/recuperar-senha/enviado/",
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_tenant_admin_cannot_receive_customer_reset_link(self):
        self.admin_a.email = "admin@example.com"
        self.admin_a.save(update_fields=["email"])
        response = self._request_reset("admin@example.com")
        self.assertRedirects(
            response,
            "/conta/recuperar-senha/enviado/",
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_valid_token_changes_password(self):
        self._request_reset()
        _, redirected = self._open_real_token()

        response = self.client.post(
            redirected,
            {
                "new_password1": self.new_password,
                "new_password2": self.new_password,
            },
            HTTP_HOST="vemdedelivery.com.br",
        )
        self.assertRedirects(
            response,
            "/conta/redefinir-senha/concluido/",
            fetch_redirect_response=False,
        )

        self.customer_user.refresh_from_db()
        self.assertFalse(self.customer_user.check_password(self.old_password))
        self.assertTrue(self.customer_user.check_password(self.new_password))

    def test_used_token_cannot_be_reused(self):
        self._request_reset()
        original_path, redirected = self._open_real_token()

        response = self.client.post(
            redirected,
            {
                "new_password1": self.new_password,
                "new_password2": self.new_password,
            },
            HTTP_HOST="vemdedelivery.com.br",
        )
        self.assertEqual(response.status_code, 302)

        self.client.cookies.clear()
        response = self.client.get(original_path, HTTP_HOST="vemdedelivery.com.br")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Link inválido ou expirado")

    def test_invalid_token_does_not_change_password(self):
        self._request_reset()
        path = self._reset_path_from_email()
        parts = path.rstrip("/").split("/")
        invalid_path = "/".join(parts[:-1] + ["token-invalido"]) + "/"

        response = self.client.get(invalid_path, HTTP_HOST="vemdedelivery.com.br")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Link inválido ou expirado")

        self.customer_user.refresh_from_db()
        self.assertTrue(self.customer_user.check_password(self.old_password))

    def test_customer_can_login_on_another_tenant_after_reset(self):
        self._request_reset(host=self.host(self.tenant_a))
        _, redirected = self._open_real_token()
        self.client.post(
            redirected,
            {
                "new_password1": self.new_password,
                "new_password2": self.new_password,
            },
            HTTP_HOST="vemdedelivery.com.br",
        )

        self.client.cookies.clear()
        response = self.client.post(
            "/conta/entrar/",
            {
                "email": self.customer_email,
                "password": self.new_password,
                "next": "/",
            },
            HTTP_HOST=self.host(self.tenant_b),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
