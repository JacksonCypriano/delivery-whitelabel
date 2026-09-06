from pathlib import Path

from django.conf import settings
from django.test import TestCase
from unfold.widgets import UnfoldBooleanSwitchWidget

from apps.billing.admin import AdditionalServiceAdminForm, BillingSettingsAdminForm, PlanAdminForm
from apps.coupons.admin import CouponCampaignAdminForm
from apps.marketplace.admin import MarketplaceProfileTenantForm
from apps.stores.admin import ProductAdminForm
from apps.tenants.admin import (
    BusinessHourInline,
    StoreSettingsAdmin,
    TenantChangeForm,
    TenantCreateForm,
)
from apps.tenants.admin_ux import BrandConfigAdminForm, BusinessHourAdminForm, DeliveryZoneAdminForm
from apps.tenants.models import BusinessHour, Tenant


class TenantAddressAdminUXCriticalTests(TestCase):
    def test_pickup_address_starts_with_cep(self):
        address_fields = None
        for title, options in StoreSettingsAdmin.fieldsets:
            if title == "Endereço para retirada":
                address_fields = options["fields"]
                break
        self.assertIsNotNone(address_fields)
        self.assertEqual(address_fields[0], "pickup_zip_code")
        self.assertEqual(address_fields[1], "pickup_address")
        self.assertEqual(address_fields[2], "pickup_number")
        self.assertEqual(address_fields[3], "pickup_complement")

    def test_tenant_form_marks_cep_and_whatsapp_for_masks(self):
        form = TenantChangeForm()
        self.assertEqual(form.fields["pickup_zip_code"].widget.attrs["data-store-cep"], "1")
        self.assertEqual(form.fields["whatsapp_number"].widget.attrs["data-store-whatsapp"], "1")
        self.assertIn("js/admin/store-settings.js", form.media._js)

    def test_store_settings_js_uses_existing_cep_api_and_focuses_number(self):
        js = (Path(settings.BASE_DIR) / "static/js/admin/store-settings.js").read_text(encoding="utf-8")
        self.assertIn("/api/cep/", js)
        self.assertIn("pickup_address", js)
        self.assertIn("pickup_neighborhood", js)
        self.assertIn("pickup_city", js)
        self.assertIn("number.focus()", js)

    def test_payment_account_cep_listener_is_delegated_and_autofills_address(self):
        js = (Path(settings.BASE_DIR) / "static/js/admin/payment-account.js").read_text(encoding="utf-8")
        self.assertIn("bindDelegatedCepLookup", js)
        self.assertIn("data-payment-cep", js)
        self.assertIn("focusout", js)
        self.assertIn("paste", js)
        self.assertIn("setFieldValue(address, data.street)", js)
        self.assertIn("setFieldValue(province, data.neighborhood)", js)

    def test_superadmin_store_form_has_guided_examples(self):
        form = TenantCreateForm()
        self.assertEqual(form.fields["slug"].widget.attrs["placeholder"], "pizzaria-do-centro")
        self.assertIn("+55", form.fields["whatsapp_number"].widget.attrs["placeholder"])
        self.assertIn("Ex.:", form.fields["merchant_name"].widget.attrs["placeholder"])


class BusinessHourAdminUXCriticalTests(TestCase):
    def test_inline_does_not_auto_render_extra_empty_weekday(self):
        self.assertEqual(BusinessHourInline.extra, 0)
        self.assertIn("is_open", BusinessHourInline.fields)
        self.assertNotIn("is_closed", BusinessHourInline.fields)

    def test_tenant_creates_seven_placeholder_days_only_once(self):
        tenant = Tenant.objects.create(
            name="Loja horários",
            slug="loja-horarios-ux",
            whatsapp_number="5511999996001",
        )
        self.assertEqual(tenant.business_hours.count(), 7)
        tenant.name = "Loja horários atualizada"
        tenant.save()
        self.assertEqual(tenant.business_hours.count(), 7)

    def test_multiple_open_intervals_same_weekday_are_allowed(self):
        tenant = Tenant.objects.create(
            name="Loja dois turnos",
            slug="loja-dois-turnos",
            whatsapp_number="5511999996002",
        )
        BusinessHour.objects.create(
            tenant=tenant,
            weekday=0,
            is_closed=False,
            opening_time="07:00",
            closing_time="12:00",
        )
        BusinessHour.objects.create(
            tenant=tenant,
            weekday=0,
            is_closed=False,
            opening_time="18:00",
            closing_time="23:00",
        )
        self.assertEqual(
            tenant.business_hours.filter(weekday=0, is_closed=False).count(),
            2,
        )

    def test_open_flag_uses_unfold_checkbox_visual_and_positive_logic(self):
        form = BusinessHourAdminForm()
        self.assertIsInstance(form.fields["is_open"].widget, UnfoldBooleanSwitchWidget)
        self.assertEqual(form.fields["is_open"].label, "Loja aberta neste horário")

    def test_short_hour_input_is_accepted_and_inverts_closed_flag(self):
        form = BusinessHourAdminForm(
            data={
                "weekday": "0",
                "is_open": "on",
                "opening_time": "07",
                "closing_time": "08",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        self.assertFalse(instance.is_closed)
        self.assertEqual(instance.opening_time.strftime("%H:%M"), "07:00")
        self.assertEqual(instance.closing_time.strftime("%H:%M"), "08:00")

    def test_closed_switch_clears_times(self):
        form = BusinessHourAdminForm(
            data={
                "weekday": "1",
                "opening_time": "09:00",
                "closing_time": "18:00",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        self.assertTrue(instance.is_closed)
        self.assertIsNone(instance.opening_time)
        self.assertIsNone(instance.closing_time)


class AdminExamplesAndListsCriticalTests(TestCase):
    def test_delivery_zone_has_currency_example(self):
        form = DeliveryZoneAdminForm()
        self.assertIn("7,50", form.fields["fee"].widget.attrs["placeholder"])
        self.assertIn("entrega grátis", form.fields["fee"].help_text)

    def test_brand_colors_use_color_picker(self):
        form = BrandConfigAdminForm()
        self.assertEqual(form.fields["primary_color"].widget.input_type, "color")
        self.assertEqual(form.fields["background_color"].widget.input_type, "color")

    def test_marketplace_profile_does_not_ask_for_discovery_location(self):
        form = MarketplaceProfileTenantForm()
        for field_name in (
            "city",
            "state",
            "neighborhood",
            "latitude",
            "longitude",
            "service_radius_km",
        ):
            self.assertNotIn(field_name, form.fields)

    def test_product_and_coupon_have_guided_numeric_examples(self):
        product = ProductAdminForm()
        coupon = CouponCampaignAdminForm()
        self.assertIn("29,90", product.fields["price"].widget.attrs["placeholder"])
        self.assertIn("10,00", coupon.fields["discount_value"].widget.attrs["placeholder"])

    def test_superadmin_billing_forms_have_examples(self):
        settings_form = BillingSettingsAdminForm()
        plan_form = PlanAdminForm()
        service_form = AdditionalServiceAdminForm()
        self.assertIn("2,99", settings_form.fields["card_percent"].widget.attrs["placeholder"])
        self.assertIn("199,00", plan_form.fields["monthly_price"].widget.attrs["placeholder"])
        self.assertIn("49,90", service_form.fields["price"].widget.attrs["placeholder"])
