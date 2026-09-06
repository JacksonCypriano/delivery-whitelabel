from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase, override_settings

from apps.billing.asaas_fields import COMPANY_TYPES
from apps.billing.models import TenantPaymentAccount
from apps.billing.online import request_subaccount
from apps.billing.provider import Asaas, ProviderRejected
from apps.tenants.admin import TenantPaymentAccountForm
from apps.tenants.models import Tenant


ASAAS_SETTINGS = dict(
    BILLING_ENABLED=True,
    ASAAS_ENVIRONMENT="sandbox",
    ASAAS_API_KEY="platform-key",
    ASAAS_WEBHOOK_TOKEN="x" * 40,
    ASAAS_WEBHOOK_URL="",
)


class PaymentAccountAsaasFormatCriticalTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja Formato Asaas",
            slug="loja-formato-asaas",
            whatsapp_number="5511999991111",
            pickup_address="Rua A",
            pickup_number="10",
            pickup_neighborhood="Centro",
            pickup_city="Itapevi",
            pickup_zip_code="06653-000",
        )

    def form_data(self, **overrides):
        data = {
            "tenant": self.tenant.pk,
            "enabled": "on",
            "terms_accepted": "True",
            "status": TenantPaymentAccount.Status.REQUESTED,
            "legal_name": "Loja Formato Asaas LTDA",
            "document": "35.381.637/0001-50",
            "email": "financeiro@example.com",
            "mobile_phone": "+55 (11) 99999-1111",
            "phone": "(11) 3230-0606",
            "birth_date": "",
            "company_type": "LIMITED",
            "income_value": "25000,00",
            "postal_code": "06653-000",
            "address": "Rua A",
            "address_number": "10",
            "complement": "Sala 2",
            "province": "Centro",
            "provider_account_id": "",
            "wallet_id": "",
            "activation_url": "",
            "last_error": "",
            "requested_at": "",
            "approved_at": "",
        }
        data.update(overrides)
        return data

    def test_company_type_is_a_select_with_only_asaas_values(self):
        form = TenantPaymentAccountForm(tenant_context=self.tenant)
        values = {value for value, _label in form.fields["company_type"].choices if value}
        self.assertEqual(values, COMPANY_TYPES)
        self.assertEqual(values, {"MEI", "LIMITED", "INDIVIDUAL", "ASSOCIATION"})

    def test_form_normalizes_document_and_brazilian_phones_before_save(self):
        form = TenantPaymentAccountForm(
            data=self.form_data(),
            instance=TenantPaymentAccount(tenant=self.tenant),
            tenant_context=self.tenant,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["document"], "35381637000150")
        self.assertEqual(form.cleaned_data["mobile_phone"], "11999991111")
        self.assertEqual(form.cleaned_data["phone"], "1132300606")
        self.assertEqual(form.cleaned_data["income_value"], Decimal("25000.00"))

    def test_cnpj_requires_company_type_and_cpf_requires_birth_date(self):
        cnpj_form = TenantPaymentAccountForm(
            data=self.form_data(company_type=""),
            instance=TenantPaymentAccount(tenant=self.tenant),
            tenant_context=self.tenant,
        )
        self.assertFalse(cnpj_form.is_valid())
        self.assertIn("company_type", cnpj_form.errors)

        cpf_form = TenantPaymentAccountForm(
            data=self.form_data(
                document="529.982.247-25",
                company_type="",
                birth_date="",
            ),
            instance=TenantPaymentAccount(tenant=self.tenant),
            tenant_context=self.tenant,
        )
        self.assertFalse(cpf_form.is_valid())
        self.assertIn("birth_date", cpf_form.errors)
        self.assertNotIn("company_type", cpf_form.errors)

    def test_prefilled_whatsapp_drops_country_code_for_asaas_field(self):
        form = TenantPaymentAccountForm(tenant_context=self.tenant)
        self.assertEqual(form.initial["mobile_phone"], "11999991111")

    def test_stable_javascript_uses_real_toggle_and_saved_backend_state(self):
        js = (Path(settings.BASE_DIR) / "static/js/admin/payment-account.js").read_text(encoding="utf-8")
        self.assertIn('input.payment-online-toggle[name$="-enabled"]', js)
        self.assertIn("paymentAccountSavedEnabled", js)
        self.assertIn("formatDocument", js)
        self.assertIn("formatPhone", js)


@override_settings(**ASAAS_SETTINGS)
class PaymentAccountActivationPersistenceCriticalTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja Persistência",
            slug="loja-persistencia",
            whatsapp_number="5511999991111",
        )
        self.account = TenantPaymentAccount.objects.create(
            tenant=self.tenant,
            enabled=True,
            terms_accepted=True,
            legal_name="Loja Persistência LTDA",
            document="35381637000150",
            email="financeiro@example.com",
            mobile_phone="5511999991111",
            phone="551132300606",
            company_type="LIMITED",
            income_value=Decimal("25000.00"),
            address="Rua A",
            address_number="10",
            province="Centro",
            postal_code="06653000",
        )

    @patch(
        "apps.billing.online.Asaas.create_subaccount",
        return_value={"id": "acc_new", "walletId": "wal_new", "apiKey": "sub-key"},
    )
    def test_success_keeps_switch_enabled_and_sends_normalized_payload(self, create_subaccount):
        result = request_subaccount(self.account)
        result.refresh_from_db()
        self.assertTrue(result.enabled)
        self.assertTrue(result.terms_accepted)
        self.assertEqual(result.status, TenantPaymentAccount.Status.PENDING)
        payload = create_subaccount.call_args.args[0]
        self.assertEqual(payload["cpfCnpj"], "35381637000150")
        self.assertEqual(payload["mobilePhone"], "11999991111")
        self.assertEqual(payload["phone"], "1132300606")
        self.assertEqual(payload["companyType"], "LIMITED")
        self.assertNotIn("birthDate", payload)

    @patch(
        "apps.billing.online.Asaas.create_subaccount",
        side_effect=ProviderRejected("Documento recusado pelo Asaas."),
    )
    def test_provider_failure_turns_switch_back_off_but_keeps_terms_and_data(self, _create):
        with self.assertRaises(ProviderRejected):
            request_subaccount(self.account)
        self.account.refresh_from_db()
        self.assertFalse(self.account.enabled)
        self.assertTrue(self.account.terms_accepted)
        self.assertEqual(self.account.status, TenantPaymentAccount.Status.ERROR)
        self.assertEqual(self.account.document, "35381637000150")
        self.assertIn("Documento recusado", self.account.last_error)


@override_settings(**ASAAS_SETTINGS)
class AsaasValidationMessageCriticalTests(TestCase):
    @patch("apps.billing.provider.requests.request")
    def test_asaas_400_description_is_preserved_for_user_correction(self, request):
        response = Mock()
        response.status_code = 400
        response.json.return_value = {
            "errors": [
                {"code": "invalid_value", "description": "O campo mobilePhone é inválido"}
            ]
        }
        request.return_value = response
        with self.assertRaises(ProviderRejected) as ctx:
            Asaas().request("POST", "/accounts", json={})
        self.assertIn("mobilePhone", str(ctx.exception))
