from decimal import Decimal

from django.conf import settings
from django.test import TestCase

from apps.billing.models import TenantPaymentAccount
from apps.tenants.admin import StoreSettingsAdmin, TenantAdmin
from apps.tenants.choices import SaleMode
from apps.orders.models import Order
from apps.orders.services import build_whatsapp_message
from apps.tenants.models import Tenant


class AdminFormVisibilityAndSaleChannelCriticalTests(TestCase):
    @staticmethod
    def _fieldset_fields(fieldsets):
        fields = []
        for _title, options in fieldsets:
            fields.extend(options.get("fields", ()))
        return fields

    def test_superadmin_does_not_expose_sale_mode(self):
        self.assertNotIn(
            "sale_mode",
            self._fieldset_fields(TenantAdmin.add_fieldsets),
        )
        self.assertNotIn(
            "sale_mode",
            self._fieldset_fields(TenantAdmin.fieldsets),
        )

    def test_tenant_admin_does_not_expose_internal_sale_mode(self):
        self.assertNotIn(
            "sale_mode",
            self._fieldset_fields(StoreSettingsAdmin.fieldsets),
        )

    def test_new_store_defaults_to_whatsapp(self):
        tenant = Tenant.objects.create(
            name="Loja padrão WhatsApp",
            slug="loja-padrao-whatsapp",
            whatsapp_number="5511999991111",
        )
        self.assertEqual(tenant.sale_mode, SaleMode.WHATSAPP)

    def test_online_payment_toggle_enables_online_without_removing_whatsapp_flow(self):
        tenant = Tenant.objects.create(
            name="Loja híbrida",
            slug="loja-hibrida",
            whatsapp_number="5511999992222",
        )
        account = TenantPaymentAccount.objects.create(
            tenant=tenant,
            enabled=True,
            terms_accepted=True,
            status=TenantPaymentAccount.Status.PENDING,
            provider_account_id="acc_test",
            encrypted_api_key="encrypted-test-key",
        )

        # Enquanto o Asaas ainda não aprovou, a loja continua integralmente
        # no fluxo de WhatsApp.
        tenant.refresh_from_db()
        self.assertEqual(tenant.sale_mode, SaleMode.WHATSAPP)

        account.status = TenantPaymentAccount.Status.APPROVED
        account.save(update_fields=["status", "updated_at"])

        tenant.refresh_from_db()
        self.assertEqual(tenant.sale_mode, SaleMode.ONLINE)

        account.enabled = False
        account.save(update_fields=["enabled", "updated_at"])

        tenant.refresh_from_db()
        self.assertEqual(tenant.sale_mode, SaleMode.WHATSAPP)


    def test_online_ready_store_still_keeps_whatsapp_order_flow(self):
        tenant = Tenant.objects.create(
            name="Loja WhatsApp e online",
            slug="loja-whatsapp-online",
            whatsapp_number="5511999993333",
        )
        account = TenantPaymentAccount.objects.create(
            tenant=tenant,
            enabled=True,
            terms_accepted=True,
            status=TenantPaymentAccount.Status.APPROVED,
            provider_account_id="acc_ready",
            encrypted_api_key="encrypted-test-key",
        )
        tenant.refresh_from_db()
        self.assertTrue(account.is_ready)
        self.assertEqual(tenant.sale_mode, SaleMode.ONLINE)

        order = Order.objects.create(
            tenant=tenant,
            customer_name="Cliente Teste",
            customer_phone="5511988887777",
            subtotal=Decimal("25.00"),
            delivery_fee=Decimal("0.00"),
            total=Decimal("25.00"),
            delivery_type="pickup",
            payment_method="cash",
        )

        message = build_whatsapp_message(order)
        self.assertTrue(message.strip())

    def test_admin_stylesheet_is_loaded_by_both_admin_sites(self):
        tenant_styles = settings.UNFOLD.get("STYLES", [])
        super_styles = settings.UNFOLD_SUPER.get("STYLES", [])

        self.assertTrue(tenant_styles)
        self.assertTrue(super_styles)
        self.assertEqual(tenant_styles[0](None), "/static/css/admin.css")
        self.assertEqual(super_styles[0](None), "/static/css/admin.css")
