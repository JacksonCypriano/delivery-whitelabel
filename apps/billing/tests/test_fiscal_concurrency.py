import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
from apps.billing.fiscal import process_fiscal
from apps.billing.models import FiscalInvoice
from . import test_fiscal as fixtures


@skipUnless(connection.vendor == "postgresql", "Concorrência fiscal exige PostgreSQL.")
@override_settings(
    BILLING_ENABLED=True,
    ASAAS_ENVIRONMENT="sandbox",
    ASAAS_API_KEY="test-only",
    ASAAS_WEBHOOK_TOKEN="testing-token-longer-than-thirty-two-characters",
)
class FiscalConcurrencyTests(TransactionTestCase):
    setUp = fixtures.FiscalTests.setUp
    payment = fixtures.FiscalTests.payment
    request = fixtures.FiscalTests.request

    def test_two_workers_create_only_one_note(self):
        barrier = threading.Barrier(2)

        def worker():
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                process_fiscal(self.bill.pk)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            for future in futures:
                future.result(timeout=30)
        self.assertEqual(FiscalInvoice.objects.count(), 1)
        self.assertEqual(len(self.posts), 1)
