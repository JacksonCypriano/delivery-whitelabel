import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import AdditionalService, Invoice
from apps.billing.provider import BillingError
from apps.billing.services import apply_payment, reserve_additional_service_invoice
from apps.tenants.models import Tenant


OPTIONS = {
    "BILLING_ENABLED": True,
    "ASAAS_ENVIRONMENT": "sandbox",
    "ASAAS_API_KEY": "test-key",
    "ASAAS_WEBHOOK_TOKEN": "test-webhook-token-with-more-than-32-characters",
}


@override_settings(**OPTIONS)
class AdditionalServiceBillingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja com assinatura", slug="loja-servico", whatsapp_number="5511988880009"
        )
        self.subscription = self.tenant.subscription
        self.subscription.managed = True
        self.subscription.valid_until = timezone.localdate() + timedelta(days=30)
        # Lojas recém-criadas começam bloqueadas; esta massa representa uma
        # assinatura já paga e liberada para contratar serviço avulso.
        self.subscription.manually_blocked = False
        self.subscription.billing_suspended = False
        self.subscription.payment_review = False
        self.subscription.save()
        self.service = AdditionalService.objects.get(code="cadastro-ate-30-produtos")

    def test_creates_additional_service_invoice_without_subscription_months(self):
        invoice = reserve_additional_service_invoice(
            self.tenant, self.service, "PIX", Decimal("249.00"), uuid.uuid4(),
            "Loja com assinatura", "12345678000190", "loja@example.com",
        )
        self.assertEqual(invoice.additional_service, self.service)
        self.assertEqual(invoice.amount, Decimal("249.00"))
        self.assertEqual(invoice.months, 0)

    def test_payment_of_additional_service_does_not_extend_subscription(self):
        invoice = Invoice.objects.create(
            tenant=self.tenant, additional_service=self.service, plan_name=self.service.name,
            months=0, amount=self.service.price, method="PIX", environment="sandbox",
            provider_id="pay_service", customer_id_external="cus_service",
            due_date=timezone.localdate() + timedelta(days=2),
        )
        previous_until = self.subscription.valid_until
        apply_payment(invoice.pk, {
            "id": "pay_service", "externalReference": invoice.reference,
            "customer": "cus_service", "billingType": "PIX", "value": "249.00",
            "status": "RECEIVED",
        })
        invoice.refresh_from_db()
        self.subscription.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(self.subscription.valid_until, previous_until)

    def test_inactive_subscription_cannot_hire_service(self):
        self.subscription.billing_suspended = True
        self.subscription.save(update_fields=["billing_suspended"])
        with self.assertRaises(BillingError):
            reserve_additional_service_invoice(
                self.tenant, self.service, "PIX", Decimal("249.00"), uuid.uuid4(),
                "Loja", "12345678000190", "loja@example.com",
            )
