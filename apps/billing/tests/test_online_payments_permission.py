from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.billing.models import TenantPaymentAccount
from apps.billing.online import request_subaccount
from apps.billing.provider import BillingError
from apps.tenants.admin import StoreSettingsAdmin, TenantPaymentAccountInline
from apps.tenants.admin_site import tenant_admin_site
from apps.tenants.models import Tenant


OPTIONS = dict(
    BILLING_ENABLED=True,
    ASAAS_ENVIRONMENT="sandbox",
    ASAAS_API_KEY="platform-key",
    ASAAS_WEBHOOK_TOKEN="x" * 40,
)


@override_settings(**OPTIONS)
class OnlinePaymentsPermissionTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja controlada",
            slug="loja-controlada",
            whatsapp_number="5511999997777",
        )
        self.account = TenantPaymentAccount.objects.create(
            tenant=self.tenant,
            enabled=True,
            terms_accepted=True,
            legal_name="Loja Controlada LTDA",
            document="35381637000150",
            email="financeiro@example.com",
            mobile_phone="11999997777",
            company_type="LIMITED",
            income_value=Decimal("5000"),
            address="Rua A",
            address_number="1",
            province="Centro",
            postal_code="01001000",
        )

    def test_new_store_starts_with_online_payments_blocked(self):
        self.assertFalse(self.tenant.online_payments_allowed)
        self.account.refresh_from_db()
        self.assertFalse(self.account.enabled)

    @patch("apps.billing.online.Asaas.create_subaccount")
    def test_backend_refuses_subaccount_when_superadmin_did_not_release(self, create):
        with self.assertRaises(BillingError):
            request_subaccount(self.account)
        create.assert_not_called()

    def test_payment_inline_is_hidden_until_store_is_released(self):
        admin = StoreSettingsAdmin(Tenant, tenant_admin_site)
        request = RequestFactory().get("/admin/tenants/tenant/1/change/")
        request.tenant = self.tenant
        self.assertNotIn(TenantPaymentAccountInline, admin.get_inlines(request, self.tenant))

        self.tenant.online_payments_allowed = True
        self.tenant.save(update_fields=["online_payments_allowed"])
        request.tenant = self.tenant
        self.assertIn(TenantPaymentAccountInline, admin.get_inlines(request, self.tenant))

    @patch("apps.billing.provider.Asaas.request")
    def test_fee_page_exists_only_for_released_store(self, request):
        User = get_user_model()
        user = User.objects.create_user(
            username="merchant-fees",
            password="Senha!123",
            is_staff=True,
            is_tenant_admin=True,
            tenant=self.tenant,
        )
        client = Client(HTTP_HOST="loja-controlada.lvh.me")
        client.force_login(user)
        url = reverse("tenant_admin:billing_online_fees")
        self.assertEqual(client.get(url).status_code, 404)

        self.tenant.online_payments_allowed = True
        self.tenant.save(update_fields=["online_payments_allowed"])
        self.account.refresh_from_db()
        self.account.provider_account_id = "acc_123"
        self.account.set_api_key("sub-key")
        self.account.save(update_fields=["provider_account_id", "encrypted_api_key"])
        request.return_value = {
            "payment": {
                "pix": {"fixedFeeValue": 1.99},
                "creditCard": {
                    "operationValue": 0.49,
                    "oneInstallmentPercentage": 2.99,
                    "upToSixInstallmentsPercentage": 3.49,
                    "upToTwelveInstallmentsPercentage": 3.99,
                    "upToTwentyOneInstallmentsPercentage": 4.29,
                    "hasValidDiscount": False,
                    "daysToReceive": 32,
                },
            }
        }
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Taxas de pagamentos online")
        self.assertContains(response, "O VemDeDelivery não cobra comissão")
        request.assert_called_once_with("GET", "/myAccount/fees/")
