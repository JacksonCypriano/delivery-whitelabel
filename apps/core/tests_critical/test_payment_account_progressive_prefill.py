from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.billing.models import BillingCustomer, TenantPaymentAccount
from apps.tenants.admin import TenantPaymentAccountForm, TenantPaymentAccountInline
from apps.tenants.models import Tenant


class PaymentAccountProgressivePrefillCriticalTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja Prefill",
            slug="loja-prefill",
            whatsapp_number="5511999993333",
            pickup_address="Rua do Cadastro",
            pickup_number="321",
            pickup_complement="Sala 4",
            pickup_neighborhood="Centro",
            pickup_city="Itapevi",
            pickup_zip_code="06653-000",
        )
        User = get_user_model()
        self.merchant = User(
            username="lojista-prefill@example.com",
            email="lojista-prefill@example.com",
            first_name="Maria",
            last_name="Silva",
            tenant=self.tenant,
            is_staff=True,
            is_tenant_admin=True,
        )
        self.merchant.set_password("Senha!123")
        self.merchant.save()

    def test_prefills_store_and_merchant_data_on_first_online_request(self):
        form = TenantPaymentAccountForm(tenant_context=self.tenant)
        self.assertEqual(form.initial["legal_name"], "Maria Silva")
        self.assertEqual(form.initial["email"], "lojista-prefill@example.com")
        self.assertEqual(form.initial["mobile_phone"], "5511999993333")
        self.assertEqual(form.initial["postal_code"], "06653-000")
        self.assertEqual(form.initial["address"], "Rua do Cadastro")
        self.assertEqual(form.initial["address_number"], "321")
        self.assertEqual(form.initial["complement"], "Sala 4")
        self.assertEqual(form.initial["province"], "Centro")

    def test_financial_customer_has_priority_for_reusable_identity_data(self):
        BillingCustomer.objects.create(
            tenant=self.tenant,
            environment="sandbox",
            name="Loja Prefill LTDA",
            document="12345678000199",
            email="financeiro@example.com",
        )
        form = TenantPaymentAccountForm(tenant_context=self.tenant)
        self.assertEqual(form.initial["legal_name"], "Loja Prefill LTDA")
        self.assertEqual(form.initial["document"], "12345678000199")
        self.assertEqual(form.initial["email"], "financeiro@example.com")

    def test_existing_payment_account_values_are_not_overwritten(self):
        account = TenantPaymentAccount.objects.create(
            tenant=self.tenant,
            legal_name="Nome já salvo",
            email="asaas-ja-salvo@example.com",
            address="Rua específica do Asaas",
        )
        form = TenantPaymentAccountForm(instance=account, tenant_context=self.tenant)
        self.assertNotEqual(form.initial.get("legal_name"), "Maria Silva")
        self.assertNotEqual(form.initial.get("email"), "lojista-prefill@example.com")
        self.assertNotEqual(form.initial.get("address"), "Rua do Cadastro")
        self.assertEqual(form.instance.legal_name, "Nome já salvo")
        self.assertEqual(form.instance.email, "asaas-ja-salvo@example.com")
        self.assertEqual(form.instance.address, "Rua específica do Asaas")

    def test_birth_date_uses_native_date_input(self):
        form = TenantPaymentAccountForm(tenant_context=self.tenant)
        self.assertEqual(form.fields["birth_date"].widget.attrs.get("type"), "date")

    def test_details_sections_are_marked_for_progressive_reveal(self):
        sections = {
            title: options.get("classes", ())
            for title, options in TenantPaymentAccountInline.fieldsets
        }
        self.assertIn("payment-online-control-section", sections["Recebimento online"])
        self.assertIn("payment-online-details-section", sections["Dados do responsável / empresa"])
        self.assertIn("payment-online-details-section", sections["Endereço"])
        self.assertIn("payment-online-details-section", sections["Integração Asaas"])
