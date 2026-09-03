import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
from django.core import mail
from apps.billing.fiscal_documents import deliver_documents
from apps.billing.models import FiscalInvoice
from . import test_fiscal_documents as fixtures


@skipUnless(
    connection.vendor == "postgresql", "Concorrência de documentos exige PostgreSQL."
)
@override_settings(
    BILLING_ENABLED=True,
    ASAAS_ENVIRONMENT="sandbox",
    ASAAS_API_KEY="test-only",
    ASAAS_WEBHOOK_TOKEN="testing-token-longer-than-thirty-two-characters",
    NFSE_SANDBOX_EMAIL_ENABLED=True,
)
class FiscalDocumentConcurrencyTests(TransactionTestCase):
    setUp = fixtures.FiscalDocumentsTests.setUp
    payment = fixtures.FiscalDocumentsTests.payment
    request = fixtures.FiscalDocumentsTests.request

    def test_two_workers_archive_and_email_once(self):
        barrier = threading.Barrier(2)

        def worker():
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                deliver_documents(self.note.pk)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            for future in futures:
                future.result(timeout=30)
        self.assertEqual(FiscalInvoice.objects.get().delivery_status, "SENT")
        self.assertEqual(len(mail.outbox), 1)
