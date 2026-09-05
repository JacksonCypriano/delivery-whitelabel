from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Tenant

# Create your tests here.


@override_settings(BILLING_ENABLED=True)
class FreeSubscriptionOnTenantCreationTests(TestCase):
    def test_admin_form_grants_one_free_month(self):
        from .admin import TenantAdmin, TenantCreateForm
        from .admin_site import super_admin_site
        from apps.billing.services import add_months

        form = TenantCreateForm(data={
            "name": "Loja cortesia", "slug": "loja-cortesia",
            "whatsapp_number": "5511999991111", "is_active": "on",
            "sale_mode": "whatsapp", "fulfillment_mode": "delivery_and_pickup",
            "grant_free_month": "on",
        })
        self.assertTrue(form.is_valid(), form.errors)
        request = RequestFactory().post("/superadmin/tenants/tenant/add/")
        request.user = get_user_model().objects.create_superuser(
            "free-month-admin", "free-month@example.com", "Senha!123"
        )
        tenant = Tenant()
        TenantAdmin(Tenant, super_admin_site).save_model(request, tenant, form, False)
        tenant.refresh_from_db()
        sub = tenant.subscription
        self.assertTrue(sub.managed)
        self.assertFalse(sub.billing_suspended)
        self.assertEqual(sub.valid_until, add_months(timezone.localdate(), 1, timezone.localdate().day))
