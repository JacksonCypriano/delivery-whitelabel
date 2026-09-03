import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
from apps.tenants.models import Tenant
from apps.billing.models import Invoice, Credit
from apps.billing.services import apply_payment, suspend_due


@skipUnless(
    connection.vendor == "postgresql", "Concorrência financeira exige PostgreSQL."
)
@override_settings(
    BILLING_ENABLED=True,
    ASAAS_ENVIRONMENT="sandbox",
    ASAAS_API_KEY="test",
    ASAAS_WEBHOOK_TOKEN="x" * 40,
)
class BillingConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Concorrência",
            slug="concorrencia-billing",
            whatsapp_number="5511988884444",
        )

    def bill(self):
        return Invoice.objects.create(
            tenant=self.tenant,
            plan_name="Mensal",
            months=1,
            method="PIX",
            amount=Decimal("199"),
            environment="sandbox",
            provider_id="pay_" + uuid.uuid4().hex,
            customer_id_external="cus_parallel",
            due_date=date(2026, 9, 5),
        )

    def payment(self, b):
        return {
            "id": b.provider_id,
            "customer": b.customer_id_external,
            "externalReference": b.reference,
            "billingType": "PIX",
            "value": 199,
            "status": "RECEIVED",
        }

    def parallel(self, functions):
        barrier = threading.Barrier(len(functions))

        def work(fn):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                return fn()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            futures = [pool.submit(work, fn) for fn in functions]
            for f in futures:
                f.result(timeout=30)

    def test_two_events_for_same_payment_credit_once(self):
        b = self.bill()
        self.parallel(
            [
                lambda: apply_payment(b.pk, self.payment(b)),
                lambda: apply_payment(b.pk, self.payment(b)),
            ]
        )
        self.assertEqual(Credit.objects.filter(invoice=b).count(), 1)

    def test_two_payments_accumulate_without_lost_month(self):
        a, b = self.bill(), self.bill()
        with patch(
            "apps.billing.services.timezone.localdate", return_value=date(2026, 9, 3)
        ):
            self.parallel(
                [
                    lambda: apply_payment(a.pk, self.payment(a)),
                    lambda: apply_payment(b.pk, self.payment(b)),
                ]
            )
        self.tenant.subscription.refresh_from_db()
        self.assertEqual(self.tenant.subscription.valid_until, date(2026, 11, 3))
        self.assertEqual(Credit.objects.count(), 2)

    def test_daily_suspension_racing_payment_finishes_active(self):
        sub = self.tenant.subscription
        sub.billing_suspended = False
        sub.valid_until = date(2026, 8, 1)
        sub.save()
        b = self.bill()
        with patch(
            "apps.billing.services.timezone.localdate", return_value=date(2026, 9, 3)
        ):
            self.parallel(
                [
                    lambda: suspend_due(date(2026, 9, 3)),
                    lambda: apply_payment(b.pk, self.payment(b)),
                ]
            )
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.is_active)
        self.assertFalse(self.tenant.subscription.billing_suspended)
