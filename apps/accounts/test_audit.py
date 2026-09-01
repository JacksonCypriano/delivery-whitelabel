import json
import re
from django.core import mail
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.test import Client, RequestFactory, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.rate_limit import get_client_ip, rate_limit_exceeded
from apps.customers.models import Customer
from apps.tenants.admin_site import super_admin_site, tenant_admin_site
from apps.tenants.models import Tenant
from .admin import SecurityEventAdmin
from .audit import record_event
from .contact_otp import save_profile, send_contact_code, verify_contact_code, cancel_contact_change
from .models import SecurityEvent, User
from .otp import OTPError, create_pending, send_code, verify_code


@override_settings(EVOLUTION_WHATSAPP_VALIDATION_ENABLED=False, OTP_TRUST_PROXY_HEADERS=False)
class SecurityAuditTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.password = "SenhaSecreta!2026"
        self.user = User.objects.create_user(username="cliente@example.com", email="cliente@example.com", first_name="Cliente", password=self.password)
        self.customer = Customer.objects.create(user=self.user, phone="11999991111")
        SecurityEvent.objects.all().delete()

    def events(self, name):
        return SecurityEvent.objects.filter(event=name)

    def registration(self):
        return create_pending(dict(first_name="Novo", last_name="Cliente", email="novo@example.com", phone="11988882222", password1=self.password))

    def contact(self):
        return save_profile(self.user.pk, dict(first_name="Cliente", last_name="Teste", email="novo@example.com", phone=self.customer.phone))[1][0]

    def send_registration(self, pending, channel="email"):
        with patch("apps.accounts.otp.deliver"), patch("apps.accounts.otp.secrets.randbelow", return_value=123456):
            send_code(pending.pk, "192.0.2.5", channel)

    def send_contact(self, pending):
        with patch("apps.accounts.contact_otp.deliver_contact_code"), patch("apps.accounts.contact_otp.secrets.randbelow", return_value=123456):
            send_contact_code(self.user.pk, pending.pk, "192.0.2.5")

    def test_login_records_actor_ip_and_route_without_credentials(self):
        response = self.client.post("/conta/entrar/?token=DO_NOT_LOG_QUERY", {
            "email": self.user.email, "password": self.password,
        }, REMOTE_ADDR="192.0.2.10", HTTP_X_REAL_IP="198.51.100.99", HTTP_USER_AGENT="DO_NOT_LOG_AGENT")
        self.assertEqual(response.status_code, 302)
        event = self.events("login_succeeded").get()
        self.assertEqual(event.user_id, self.user.pk)
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertEqual(event.ip_address, "192.0.2.10")
        self.assertEqual(event.route, "customer_accounts:login")
        self.assertTrue(event.request_id)
        dump = json.dumps(list(SecurityEvent.objects.values()), default=str)
        for secret in [self.password, "DO_NOT_LOG_QUERY", "DO_NOT_LOG_AGENT"]:
            self.assertNotIn(secret, dump)

    def test_wrong_login_is_recorded_once_with_protected_identifier(self):
        self.client.post("/conta/entrar/", {"email": self.user.email, "password": "DO_NOT_LOG_PASSWORD"})
        event = self.events("login_failed").get()
        self.assertEqual(event.reason, "invalid_credentials")
        self.assertEqual(len(event.identifier_hash), 64)
        self.assertIsNone(event.user_id)
        self.assertNotIn(self.user.email, json.dumps(list(SecurityEvent.objects.values()), default=str))

    def test_invalid_login_fields_are_recorded(self):
        self.client.post("/conta/entrar/", {"email": "not-an-email", "password": "secret"})
        self.assertEqual(self.events("login_failed").get().reason, "invalid_input")

    def test_blocked_login_does_not_authenticate(self):
        for _ in range(8):
            self.client.post("/conta/entrar/", {"email": self.user.email, "password": "wrong"})
        with patch("apps.accounts.forms.authenticate") as auth:
            self.client.post("/conta/entrar/", {"email": self.user.email, "password": self.password})
            auth.assert_not_called()
        self.assertEqual(self.events("rate_limited").get().reason, "rate_limit")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_records_user_before_session_is_cleared(self):
        self.client.force_login(self.user)
        self.client.post("/conta/sair/")
        event = self.events("logout").get()
        self.assertEqual(event.user_id, self.user.pk)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_django_auth_signal_records_without_http_request(self):
        authenticate(username=self.user.email, password="wrong")
        event = self.events("login_failed").get()
        self.assertEqual(event.route, "")
        self.assertIsNone(event.ip_address)

    def test_registration_events_do_not_store_code_or_password(self):
        pending = self.registration()
        self.send_registration(pending)
        verify_code(pending.pk, "email", "123456")
        self.send_registration(pending, "whatsapp")
        user = verify_code(pending.pk, "whatsapp", "123456")
        self.assertEqual(self.events("registration_started").count(), 1)
        self.assertEqual(self.events("otp_sent").count(), 2)
        self.assertEqual(self.events("otp_confirmed").count(), 2)
        self.assertEqual(self.events("account_created").get().user_id, user.pk)
        self.assertEqual(self.events("otp_confirmed").filter(channel="whatsapp").get().user_id, user.pk)
        dump = json.dumps(list(SecurityEvent.objects.values()), default=str)
        for secret in ["123456", self.password, pending.password_hash, "novo@example.com", "11988882222"]:
            self.assertNotIn(secret, dump)

    def test_otp_wrong_and_attempts_block_are_distinct(self):
        pending = self.registration()
        self.send_registration(pending)
        for _ in range(5):
            with self.assertRaises(OTPError):
                verify_code(pending.pk, "email", "000000")
        with self.assertRaises(OTPError):
            verify_code(pending.pk, "email", "123456")
        self.assertEqual(self.events("otp_rejected").filter(reason="invalid_code").count(), 5)
        self.assertEqual(self.events("rate_limited").get().reason, "attempts")

    def test_otp_cooldown_is_audited(self):
        pending = self.registration()
        self.send_registration(pending)
        with self.assertRaises(OTPError):
            self.send_registration(pending)
        self.assertEqual(self.events("rate_limited").get().reason, "cooldown")
        self.assertEqual(self.events("otp_sent").count(), 1)

    def test_provider_failure_has_no_raw_exception(self):
        pending = self.registration()
        with patch("apps.accounts.otp.deliver", side_effect=RuntimeError("secret-api-key 123456")):
            with self.assertRaises(OTPError):
                send_code(pending.pk, "192.0.2.5", "email")
        self.assertEqual(self.events("otp_delivery_failed").get().reason, "delivery")
        self.assertFalse(self.events("otp_sent").exists())
        self.assertNotIn("secret-api-key", json.dumps(list(SecurityEvent.objects.values()), default=str))

    def test_contact_confirmation_records_change_once(self):
        pending = self.contact()
        self.assertEqual(self.events("contact_requested").get().user_id, self.user.pk)
        self.assertFalse(self.events("email_changed").exists())
        self.send_contact(pending)
        verify_contact_code(self.user.pk, pending.pk, "123456")
        self.assertEqual(self.events("email_changed").count(), 1)
        self.assertEqual(self.events("otp_confirmed").get().scope, "contact")
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "123456")
        self.assertEqual(self.events("email_changed").count(), 1)

    def test_cancellation_is_audited_without_contact_change(self):
        pending = self.contact()
        cancel_contact_change(self.user.pk, pending.pk)
        self.assertEqual(self.events("contact_cancelled").get().reference, pending.pk)
        self.assertFalse(self.events("email_changed").exists())

    def test_phone_change_is_audited(self):
        pending = save_profile(self.user.pk, dict(first_name="Cliente", last_name="Teste", email=self.user.email, phone="11988882222"))[1][0]
        self.send_contact(pending)
        verify_contact_code(self.user.pk, pending.pk, "123456")
        self.assertEqual(self.events("phone_changed").get().user_id, self.user.pk)

    def test_password_change_is_audited_without_hash(self):
        self.client.force_login(self.user)
        new_password = "NovaSenhaForte!2026"
        self.client.post("/conta/alterar-senha/", {"old_password": self.password, "new_password1": new_password, "new_password2": new_password})
        event = self.events("password_changed").get()
        self.assertEqual(event.user_id, self.user.pk)
        self.user.refresh_from_db()
        dump = json.dumps(list(SecurityEvent.objects.values()), default=str)
        for secret in [self.password, new_password, self.user.password]:
            self.assertNotIn(secret, dump)

    def test_password_reset_unknown_account_keeps_generic_response(self):
        response = self.client.post("/conta/recuperar-senha/", {"email": "unknown@example.com"})
        self.assertEqual(response.status_code, 302)
        event = self.events("password_reset_requested").get()
        self.assertIsNone(event.user_id)
        self.assertEqual(len(event.identifier_hash), 64)

    @override_settings(CUSTOMER_PORTAL_URL="https://vemdedelivery.com.br")
    def test_password_reset_completion_records_no_reset_token(self):
        self.client.post("/conta/recuperar-senha/", {"email": self.user.email})
        path = re.search(r"https://vemdedelivery\.com\.br(/conta/redefinir-senha/[^\s]+)", mail.outbox[-1].body).group(1)
        token = path.rstrip("/").split("/")[-1]
        response = self.client.get(path)
        new_password = "SenhaRecriada!2026"
        response = self.client.post(response.url, {"new_password1": new_password, "new_password2": new_password})
        self.assertEqual(response.status_code, 302)
        event = self.events("password_changed").get()
        self.assertEqual(event.route, "customer_accounts:password-reset-confirm")
        dump = json.dumps(list(SecurityEvent.objects.values()), default=str)
        self.assertNotIn(token, dump)
        self.assertNotIn(new_password, dump)

    def test_duplicate_contact_failure_has_no_success_event(self):
        pending = self.contact()
        self.send_contact(pending)
        User.objects.create_user(username="novo@example.com", email="novo@example.com", password=self.password)
        with self.assertRaises(OTPError):
            verify_contact_code(self.user.pk, pending.pk, "123456")
        self.assertFalse(self.events("email_changed").exists())
        self.assertFalse(self.events("otp_confirmed").exists())
        self.assertEqual(self.events("otp_rejected").get().reason, "rejected")

    def test_rolled_back_contact_change_has_no_success_event(self):
        with self.assertRaises(ValueError):
            with transaction.atomic():
                self.user.email = "rollback@example.com"
                self.user.save(update_fields=["email"])
                raise ValueError("abort")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "cliente@example.com")
        self.assertFalse(self.events("email_changed").exists())

    def test_event_waits_for_outer_commit(self):
        with transaction.atomic():
            record_event("password_changed", user_id=self.user.pk)
            self.assertFalse(self.events("password_changed").exists())
        self.assertEqual(self.events("password_changed").count(), 1)

    def test_audit_write_failure_does_not_break_login_or_leak_exception(self):
        with patch("apps.accounts.audit.SecurityEvent.objects.create", side_effect=DatabaseError("DO_NOT_LOG_THIS")):
            with self.assertLogs("vemdedelivery.audit", level="ERROR") as logs:
                response = self.client.post("/conta/entrar/", {"email": self.user.email, "password": self.password})
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertNotIn("DO_NOT_LOG_THIS", " ".join(logs.output))

    def test_request_context_is_cleared_before_background_event(self):
        self.client.post("/conta/entrar/", {"email": self.user.email, "password": self.password})
        record_event("password_changed", user_id=self.user.pk)
        event = self.events("password_changed").get()
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.request_id, "")
        self.assertEqual(event.route, "")

    def test_unknown_reason_and_channel_are_not_stored_verbatim(self):
        record_event("otp_rejected", user_id=self.user.pk, reason="LEAK_REASON", channel="LEAK_CHANNEL")
        event = self.events("otp_rejected").get()
        self.assertEqual(event.reason, "rejected")
        self.assertEqual(event.channel, "")

    def test_superadmin_can_read_but_not_mutate(self):
        admin = User.objects.create_superuser(username="root", email="root@example.com", password=self.password)
        record_event("password_changed", user_id=self.user.pk)
        event = self.events("password_changed").get()
        self.client.force_login(admin)
        url = reverse("super_admin:accounts_securityevent_changelist")
        self.assertContains(self.client.get(url), "Eventos de segurança")
        detail = reverse("super_admin:accounts_securityevent_change", args=[event.pk])
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.post(detail, {"reason": "unexpected"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("super_admin:accounts_securityevent_add")).status_code, 403)
        delete = reverse("super_admin:accounts_securityevent_delete", args=[event.pk])
        self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)
        response = self.client.post(url, {"action": "delete_selected", "_selected_action": [event.pk]})
        self.assertTrue(SecurityEvent.objects.filter(pk=event.pk).exists())

    def test_customer_and_tenant_admin_cannot_read_audit(self):
        tenant = Tenant.objects.create(name="Loja", slug="loja")
        staff = User.objects.create_user(username="staff", password=self.password, tenant=tenant, is_staff=True, is_tenant_admin=True)
        url = reverse("super_admin:accounts_securityevent_changelist")
        for user in [self.user, staff]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 302)
            request = RequestFactory().get(url)
            request.user = user
            model_admin = SecurityEventAdmin(SecurityEvent, super_admin_site)
            self.assertFalse(model_admin.has_view_permission(request))
            self.assertFalse(model_admin.get_queryset(request).exists())
        self.assertNotIn(SecurityEvent, tenant_admin_site._registry)

    def test_deleted_user_keeps_audit_event(self):
        record_event("password_changed", user_id=self.user.pk)
        event = self.events("password_changed").get()
        self.user.delete()
        event.refresh_from_db()
        self.assertIsNone(event.user_id)
        self.assertEqual(event.event, "password_changed")

    def test_dashboard_login_and_refresh_audit(self):
        tenant = Tenant.objects.create(name="Loja", slug="loja")
        admin = User.objects.create_user(username="staff", password=self.password, tenant=tenant, is_staff=True, is_tenant_admin=True)
        client = APIClient()
        response = client.post("/dashboard/auth/login/", {"username": "staff", "password": self.password}, HTTP_HOST="loja.lvh.me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.events("login_succeeded").get().user_id, admin.pk)
        token = response.data["refresh"]
        response = client.post("/dashboard/auth/refresh/", {"refresh": token}, HTTP_HOST="loja.lvh.me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.events("token_refreshed").count(), 1)
        self.assertNotIn(token, json.dumps(list(SecurityEvent.objects.values()), default=str))

    def test_dashboard_logout_cannot_blacklist_someone_elses_token(self):
        other = User.objects.create_user(username="other", password=self.password)
        token = RefreshToken.for_user(other)
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post("/dashboard/auth/logout/", {"refresh": str(token)})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BlacklistedToken.objects.filter(token__jti=token["jti"]).exists())
        self.assertEqual(self.events("access_denied").get().reason, "not_allowed")

    def test_dashboard_logout_accepts_own_token(self):
        token = RefreshToken.for_user(self.user)
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post("/dashboard/auth/logout/", {"refresh": str(token)})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=token["jti"]).exists())
        self.assertEqual(self.events("logout").get().user_id, self.user.pk)

    def test_spoofed_proxy_headers_do_not_bypass_limits(self):
        factory = RequestFactory()
        for i in range(5):
            request = factory.get("/", REMOTE_ADDR="192.0.2.10", HTTP_X_REAL_IP=f"198.51.100.{i}", HTTP_X_FORWARDED_FOR=f"203.0.113.{i}")
            self.assertFalse(rate_limit_exceeded(request, "audit-test", limit=5))
        request = factory.get("/", REMOTE_ADDR="192.0.2.10", HTTP_X_REAL_IP="198.51.100.99")
        self.assertTrue(rate_limit_exceeded(request, "audit-test", limit=5))

    @override_settings(OTP_TRUST_PROXY_HEADERS=True)
    def test_explicit_trusted_proxy_uses_validated_real_ip(self):
        request = RequestFactory().get("/", REMOTE_ADDR="192.0.2.10", HTTP_X_REAL_IP="2001:db8::1")
        self.assertEqual(get_client_ip(request), "2001:db8::1")
        request.META["HTTP_X_REAL_IP"] = "invalid\n123456"
        self.assertEqual(get_client_ip(request), "unknown")
