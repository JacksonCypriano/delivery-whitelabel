from django.conf import settings
from django.test import RequestFactory

from apps.tenants.admin_site import tenant_admin_site

from .base import CriticalTestCase


class TenantAdminPriorityDropdownCriticalTests(CriticalTestCase):
    def setUp(self):
        self.client.force_login(self.admin_a)

    def test_tenant_sidebar_follows_onboarding_priority(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        self.assertEqual(
            [str(group["title"]) for group in navigation],
            ["Comece por aqui", "Cardápio", "Operação", "Marketing", "Financeiro"],
        )
        self.assertTrue(all(group.get("collapsible") for group in navigation))

        first_group = navigation[0]
        self.assertEqual(
            [str(item["title"]) for item in first_group["items"]],
            [
                "Minha loja",
                "Perfil público",
                "Identidade visual",
                "Horários de funcionamento",
                "Locais e taxas de entrega",
            ],
        )

        for group in navigation:
            for item in group["items"]:
                self.assertTrue(str(item["link"]).startswith("/admin/"))

    def test_tenant_dashboard_uses_collapsible_priority_template(self):
        self.assertEqual(tenant_admin_site.index_template, "admin/tenant/index.html")

        response = self.client.get("/admin/", HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Comece por aqui — configuração inicial")
        self.assertContains(response, '<details class="app-tenants module">', html=False)
        self.assertContains(response, '<details class="app-stores module">', html=False)
        self.assertNotContains(response, '<details class="app-tenants module" open', html=False)

    def test_tenant_dashboard_apps_and_models_are_prioritized(self):
        request = RequestFactory().get("/admin/")
        request.user = self.admin_a
        request.tenant = self.tenant_a

        app_list = tenant_admin_site.get_app_list(request)
        labels = [app["app_label"] for app in app_list]
        expected = [
            label
            for label in ("tenants", "marketplace", "stores", "orders", "customers", "coupons")
            if label in labels
        ]
        self.assertEqual(labels[:len(expected)], expected)

        tenants_app = next((app for app in app_list if app["app_label"] == "tenants"), None)
        if tenants_app:
            names = [model["object_name"] for model in tenants_app["models"]]
            preferred = [
                name
                for name in ("Tenant", "BrandConfig", "BusinessHour", "DeliveryZone")
                if name in names
            ]
            self.assertEqual(names[:len(preferred)], preferred)

        stores_app = next((app for app in app_list if app["app_label"] == "stores"), None)
        if stores_app:
            names = [model["object_name"] for model in stores_app["models"]]
            preferred = [
                name
                for name in ("Category", "Product", "CustomizationGroup", "CustomizationGroupLabel")
                if name in names
            ]
            self.assertEqual(names[:len(preferred)], preferred)
