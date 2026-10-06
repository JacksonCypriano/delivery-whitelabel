from django.contrib.auth import SESSION_KEY
from django.test import Client

from .base import CriticalTestCase


class PanelHostIsolationCriticalTests(CriticalTestCase):
    platform_host = "lvh.me"

    def test_same_painel_path_selects_scope_by_host(self):
        merchant = self.client.get("/painel/", HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(merchant.status_code, 200)
        self.assertContains(merchant, 'kind:"merchant"')
        self.assertContains(merchant, 'apiBase:"/api/merchant/"')

        platform = self.client.get("/painel/", HTTP_HOST=self.platform_host)
        self.assertEqual(platform.status_code, 200)
        self.assertContains(platform, 'kind:"superadmin"')
        self.assertContains(platform, 'apiBase:"/api/superadmin/"')

    def test_unknown_subdomain_does_not_fall_back_to_global_admin(self):
        response = self.client.get("/painel/", HTTP_HOST="nao-existe.lvh.me")
        self.assertEqual(response.status_code, 404)

    def test_superadmin_credentials_are_rejected_by_merchant_login(self):
        client = Client(HTTP_HOST=self.host(self.tenant_a))
        response = client.post(
            "/api/merchant/session/",
            {"username": self.superuser.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(SESSION_KEY, client.session)

    def test_merchant_credentials_are_rejected_by_global_login(self):
        client = Client(HTTP_HOST=self.platform_host)
        response = client.post(
            "/api/superadmin/session/",
            {"username": self.admin_a.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(SESSION_KEY, client.session)

    def test_merchant_credentials_are_rejected_by_other_tenant(self):
        client = Client(HTTP_HOST=self.host(self.tenant_b))
        response = client.post(
            "/api/merchant/session/",
            {"username": self.admin_a.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(SESSION_KEY, client.session)

    def test_cross_scope_api_calls_fail_even_with_existing_sessions(self):
        merchant = Client(HTTP_HOST=self.platform_host)
        merchant.force_login(self.admin_a)
        self.assertEqual(merchant.get("/api/merchant/dashboard/").status_code, 404)
        self.assertEqual(merchant.get("/api/superadmin/dashboard/").status_code, 403)

        root = Client(HTTP_HOST=self.host(self.tenant_a))
        root.force_login(self.superuser)
        self.assertEqual(root.get("/api/superadmin/dashboard/").status_code, 404)
        self.assertEqual(root.get("/api/merchant/dashboard/").status_code, 403)
