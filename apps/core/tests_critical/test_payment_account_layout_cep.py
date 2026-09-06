from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.contrib import admin
from django.conf import settings
from pathlib import Path

from apps.billing.models import TenantPaymentAccount
from apps.tenants.admin import TenantPaymentAccountForm, TenantPaymentAccountInline
from apps.tenants.admin_site import tenant_admin_site
from apps.tenants.models import Tenant


class PaymentAccountLayoutCepCriticalTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja CEP",
            slug="loja-cep",
            whatsapp_number="5511999994444",
        )

    def test_payment_account_uses_stacked_vertical_inline(self):
        # O cadastro financeiro não deve voltar para a tabela horizontal.
        self.assertFalse(issubclass(TenantPaymentAccountInline, admin.TabularInline))

    def test_address_section_starts_with_postal_code(self):
        address_fields = None
        for title, options in TenantPaymentAccountInline.fieldsets:
            if title == "Endereço":
                address_fields = options["fields"]
                break
        self.assertIsNotNone(address_fields)
        self.assertEqual(address_fields[0], "postal_code")
        self.assertEqual(
            address_fields,
            ("postal_code", "address", "address_number", "complement", "province"),
        )

    def test_form_uses_v9_assets_and_cep_marker(self):
        form = TenantPaymentAccountForm()
        self.assertEqual(form.media._js, ["js/admin/payment-account-v9.js"])
        self.assertIn("css/admin/payment-account-v9.css", form.media._css.get("all", []))
        self.assertEqual(form.fields["postal_code"].widget.attrs["data-payment-cep"], "1")
        self.assertEqual(form.fields["postal_code"].widget.attrs["placeholder"], "00000-000")

    def test_existing_payment_account_does_not_render_extra_blank_form(self):
        TenantPaymentAccount.objects.create(tenant=self.tenant)
        inline = TenantPaymentAccountInline(Tenant, tenant_admin_site)
        request = RequestFactory().get("/admin/tenants/tenant/1/change/")
        self.assertEqual(inline.get_extra(request, self.tenant), 0)

    def test_new_payment_account_keeps_one_form_available(self):
        inline = TenantPaymentAccountInline(Tenant, tenant_admin_site)
        request = RequestFactory().get("/admin/tenants/tenant/1/change/")
        self.assertEqual(inline.get_extra(request, self.tenant), 1)


class PaymentAccountProgressiveAssetsV9CriticalTests(TestCase):
    def test_v9_initializes_from_enabled_field_instead_of_inline_related(self):
        js = (Path(settings.BASE_DIR) / "static/js/admin/payment-account-v9.js").read_text(encoding="utf-8")
        self.assertIn("input.payment-online-toggle", js)
        self.assertIn("inlineRootFor(enabledInput)", js)
        self.assertNotIn("querySelectorAll('.payment-account-inline .inline-related')", js)

    def test_v9_hides_detail_sections_until_progressive_flow_is_active(self):
        css = (Path(settings.BASE_DIR) / "static/css/admin/payment-account-v9.css").read_text(encoding="utf-8")
        self.assertIn(".payment-account-inline .payment-online-details-section", css)
        self.assertIn(".payment-online-details-visible", css)


class PaymentAccountCompactHeaderV9CriticalTests(TestCase):
    def test_status_is_not_rendered_as_separate_form_row(self):
        control_fields = None
        for title, options in TenantPaymentAccountInline.fieldsets:
            if title == "Recebimento online":
                control_fields = options["fields"]
                break
        self.assertEqual(control_fields, ("terms_accepted", "enabled"))

    def test_saved_status_is_sent_to_compact_switch_by_data_attribute(self):
        tenant = Tenant.objects.create(
            name="Loja Status",
            slug="loja-status",
            whatsapp_number="5511999995555",
        )
        account = TenantPaymentAccount.objects.create(
            tenant=tenant,
            status=TenantPaymentAccount.Status.PENDING,
        )
        form = TenantPaymentAccountForm(instance=account, tenant_context=tenant)
        self.assertEqual(
            form.fields["enabled"].widget.attrs["data-payment-account-status"],
            account.get_status_display(),
        )

    def test_v9_hides_technical_inline_heading_and_aligns_compact_card(self):
        js = (Path(settings.BASE_DIR) / "static/js/admin/payment-account-v9.js").read_text(encoding="utf-8")
        css = (Path(settings.BASE_DIR) / "static/css/admin/payment-account-v9.css").read_text(encoding="utf-8")
        self.assertIn("hideTechnicalInlineHeading", js)
        self.assertIn("data-payment-account-status", (Path(settings.BASE_DIR) / "apps/tenants/admin.py").read_text(encoding="utf-8"))
        self.assertIn("grid-template-columns: 46px", css)
        self.assertIn("padding-left: 16px", css)
