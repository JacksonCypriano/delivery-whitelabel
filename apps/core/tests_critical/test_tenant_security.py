from django.contrib.auth import SESSION_KEY
from django.test import Client
from django.urls import reverse

from .base import CriticalTestCase


class TenantSecurityCriticalTests(CriticalTestCase):
    def test_tenant_middleware_resolves_subdomain(self):
        response = self.client.get("/", HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.wsgi_request.tenant, self.tenant_a)

    def test_superadmin_has_no_tenant(self):
        response = self.client.get("/superadmin/login/", HTTP_HOST=self.host(self.tenant_a))
        self.assertIsNone(response.wsgi_request.tenant)

    def test_correct_tenant_admin_can_login(self):
        response = self.client.post("/admin/login/?next=/admin/", {"username": self.admin_a.username, "password": self.password, "next": "/admin/"}, HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.status_code, 302)
        self.assertIn(SESSION_KEY, self.client.session)

    def test_wrong_tenant_admin_is_rejected_without_session(self):
        client = Client()
        response = client.post("/admin/login/?next=/admin/", {"username": self.admin_a.username, "password": self.password, "next": "/admin/"}, HTTP_HOST=self.host(self.tenant_b))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, client.session)
        self.assertContains(response, "Credenciais inválidas para esta loja.")

    def test_superuser_cannot_enter_tenant_admin(self):
        client = Client()
        response = client.post("/admin/login/?next=/admin/", {"username": self.superuser.username, "password": self.password, "next": "/admin/"}, HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, client.session)

    def test_tenant_create_api_rejects_anonymous(self):
        response = self.client.post("/api/tenants/create/", {}, content_type="application/json", HTTP_HOST="vemdedelivery.com.br")
        self.assertIn(response.status_code, (401, 403))

    def test_tenant_create_api_rejects_tenant_admin(self):
        self.client.force_login(self.admin_a)
        response = self.client.post("/api/tenants/create/", {}, content_type="application/json", HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_token_login_rejects_admin_from_other_tenant(self):
        response = self.client.post("/dashboard/auth/login/", {"username": self.admin_a.username, "password": self.password}, content_type="application/json", HTTP_HOST=self.host(self.tenant_b))
        self.assertEqual(response.status_code, 403)
