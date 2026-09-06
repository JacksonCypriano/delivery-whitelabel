from django.test import RequestFactory

from apps.tenants.admin_site import super_admin_site

from .base import CriticalTestCase


class SuperAdminDashboardDropdownCriticalTests(CriticalTestCase):
    def setUp(self):
        self.client.force_login(self.superuser)

    def test_superadmin_uses_collapsible_dashboard_template(self):
        self.assertEqual(super_admin_site.index_template, "admin/super/index.html")

        response = self.client.get("/superadmin/", HTTP_HOST="vemdedelivery.com.br")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<details class="app-tenants module">', html=False)
        self.assertContains(response, '<details class="app-billing module">', html=False)
        self.assertContains(response, '<details class="app-integrations module">', html=False)

    def test_superadmin_dashboard_apps_are_in_operational_order(self):
        request = RequestFactory().get("/superadmin/")
        request.user = self.superuser
        request.tenant = None

        labels = [app["app_label"] for app in super_admin_site.get_app_list(request)]
        expected = [
            label
            for label in ("tenants", "accounts", "billing", "integrations", "marketplace")
            if label in labels
        ]
        self.assertEqual(labels[:len(expected)], expected)

        billing = next(
            (app for app in super_admin_site.get_app_list(request) if app["app_label"] == "billing"),
            None,
        )
        if billing:
            names = [model["object_name"] for model in billing["models"]]
            preferred = [
                name
                for name in ("Subscription", "Invoice", "Credit", "Plan", "AdditionalService")
                if name in names
            ]
            self.assertEqual(names[:len(preferred)], preferred)
