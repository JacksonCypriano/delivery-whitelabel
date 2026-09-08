from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.fiscal_models import fiscal_today
from apps.billing.models import (
    FiscalInvoice,
    FiscalSettings,
    Invoice,
    Subscription,
    TaxRate,
)
from apps.tenants.models import Tenant


class OperationalChecksTests(TestCase):
    def test_check_billing_counts_only_active_tenants(self):
        active = Tenant.objects.create(
            name="Ativa", slug="check-ativa", whatsapp_number="5511999997001"
        )
        archived = Tenant.objects.create(
            name="Arquivada", slug="check-arquivada", whatsapp_number="5511999997002"
        )
        Tenant.objects.filter(pk=active.pk).update(is_active=True)
        Tenant.objects.filter(pk=archived.pk).update(is_active=False)
        Subscription.objects.filter(tenant=active).update(managed=True)
        Subscription.objects.filter(tenant=archived).update(managed=False)

        out = StringIO()
        with override_settings(BILLING_ENABLED=False):
            call_command("check_billing", stdout=out)

        text = out.getvalue()
        self.assertIn("Lojas ativas com controle: 1; sem controle: 0", text)

    @override_settings(
        BILLING_ENABLED=True,
        BILLING_ALLOW_SANDBOX=True,
        ASAAS_ENVIRONMENT="sandbox",
        ASAAS_API_KEY="test-key",
        ASAAS_WEBHOOK_TOKEN="test-webhook-token-with-more-than-32-characters",
    )
    def test_check_nfse_treats_canceled_as_terminal(self):
        config = FiscalSettings.objects.create(
            environment="sandbox",
            enabled=True,
            start_at=timezone.now() - timedelta(days=1),
            service_code="02800",
            fiscal_email="fiscal@example.com",
            municipal_inscription="16739426",
            cnae="6202300",
            special_tax_regime="0",
            national_portal_tax_calculation_regime="1",
            nbs_code="1.1103.22.00",
            rps_serie="1",
            rps_number=1,
        )
        TaxRate.objects.create(
            configuration=config,
            month=fiscal_today().replace(day=1),
            iss="2.01",
            checked_at=timezone.now(),
        )
        tenant = Tenant.objects.create(
            name="Fiscal check",
            slug="fiscal-check",
            whatsapp_number="5511999997003",
        )

        def make_note(status, suffix, review_required=False):
            invoice = Invoice.objects.create(
                tenant=tenant,
                plan_name="Teste",
                months=1,
                amount="5.00",
                method="PIX",
                environment="sandbox",
                provider_id=f"pay_{suffix}",
                customer_id_external="cus_check",
                status="PAID",
                due_date=fiscal_today(),
                paid_at=timezone.now(),
            )
            return FiscalInvoice.objects.create(
                invoice=invoice,
                provider_id=f"inv_{suffix}",
                status=status,
                amount="5.00",
                review_required=review_required,
            )

        make_note("AUTHORIZED", "authorized")
        make_note("CANCELED", "canceled", review_required=True)

        out = StringIO()
        call_command("check_nfse", stdout=out)
        text = out.getvalue()
        self.assertIn(
            "Notas pendentes de conclusão: 0; em revisão fiscal: 0; canceladas: 1.",
            text,
        )

        make_note("ERROR", "error", review_required=True)
        out = StringIO()
        call_command("check_nfse", stdout=out)
        text = out.getvalue()
        self.assertIn(
            "Notas pendentes de conclusão: 1; em revisão fiscal: 1; canceladas: 1.",
            text,
        )
