from django.test import SimpleTestCase

from apps.billing.admin import EventAdmin, PlanAdmin
from apps.billing.models import BillingEvent, Invoice, Plan
from apps.orders.models import Order
from apps.stores.models import Product
from apps.tenants.admin_site import super_admin_site, tenant_admin_site


class AdminPortugueseTests(SimpleTestCase):
    def test_admin_sites_and_primary_fields_are_in_portuguese(self):
        self.assertEqual(tenant_admin_site.site_header, "Painel da loja")
        self.assertEqual(super_admin_site.site_title, "Administração global")
        self.assertEqual(Product._meta.get_field("sale_price").verbose_name, "Preço promocional")
        self.assertEqual(Product._meta.get_field("is_available").verbose_name, "Disponível")
        self.assertEqual(Order._meta.get_field("status").verbose_name, "Situação")
        self.assertEqual(Invoice._meta.get_field("environment").flatchoices[0][1], "Ambiente de testes")

    def test_computed_superadmin_columns_have_portuguese_titles(self):
        plan_admin = PlanAdmin(Plan, super_admin_site)
        event_admin = EventAdmin(BillingEvent, super_admin_site)
        self.assertEqual(plan_admin.plan_price.short_description, "Valor do plano")
        self.assertEqual(event_admin.event_kind.short_description, "Tipo da notificação")
