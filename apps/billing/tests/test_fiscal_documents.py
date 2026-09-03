import hashlib
from unittest.mock import patch, Mock
from django.test import TestCase, Client, override_settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.billing.models import FiscalInvoice, BillingCustomer, MunicipalExport
from apps.billing.fiscal import process_fiscal
from apps.billing.fiscal_documents import (
    deliver_documents,
    download_document,
    attachment_response,
    LIMIT,
)
from django.http import Http404
from . import test_fiscal as fixtures

PDF = b"%PDF-1.4\nfixture document\n%%EOF"
XML = b'<?xml version="1.0"?><NFSe><Numero>123</Numero></NFSe>'


@override_settings(
    BILLING_ENABLED=True,
    ASAAS_ENVIRONMENT="sandbox",
    ASAAS_API_KEY="test-only",
    ASAAS_WEBHOOK_TOKEN="testing-token-longer-than-thirty-two-characters",
    NFSE_SANDBOX_EMAIL_ENABLED=True,
)
class FiscalDocumentsTests(TestCase):
    payment = fixtures.FiscalTests.payment
    request = fixtures.FiscalTests.request

    def setUp(self):
        fixtures.FiscalTests.setUp(self)
        process_fiscal(self.bill.pk)
        self.note = FiscalInvoice.objects.get()
        self.note.xml_url = "https://example.com/note.xml"
        self.note.save()
        BillingCustomer.objects.create(
            tenant=self.tenant,
            environment="sandbox",
            name="Loja",
            document="123",
            email="financeiro@example.com",
            provider_id="cus_fiscal",
        )
        patcher = patch(
            "apps.billing.fiscal_documents.download_document",
            side_effect=lambda url, kind: PDF if kind == "pdf" else XML,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_archives_pdf_xml_and_sends_once(self):
        deliver_documents(self.note.pk)
        deliver_documents(self.note.pk)
        self.note.refresh_from_db()
        self.assertEqual(bytes(self.note.pdf_content), PDF)
        self.assertEqual(bytes(self.note.xml_content), XML)
        self.assertEqual(self.note.pdf_sha256, hashlib.sha256(PDF).hexdigest())
        self.assertEqual(self.note.delivery_status, "SENT")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["financeiro@example.com"])
        self.assertEqual(len(mail.outbox[0].attachments), 2)

    def test_no_email_before_authorized(self):
        self.note.status = "SCHEDULED"
        self.note.save()
        deliver_documents(self.note.pk)
        self.assertEqual(len(mail.outbox), 0)

    def test_missing_xml_does_not_block_pdf_email(self):
        self.note.xml_url = ""
        self.note.save()
        deliver_documents(self.note.pk)
        self.assertEqual(len(mail.outbox[0].attachments), 1)

    @override_settings(NFSE_SANDBOX_EMAIL_ENABLED=False)
    def test_sandbox_email_off_still_archives(self):
        deliver_documents(self.note.pk)
        self.note.refresh_from_db()
        self.assertTrue(self.note.pdf_content)
        self.assertEqual(len(mail.outbox), 0)

    def test_missing_pdf_waits(self):
        self.note.pdf_url = ""
        self.note.save()
        deliver_documents(self.note.pk)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(FiscalInvoice.objects.get().delivery_status, "PENDING")

    def test_smtp_uncertainty_never_auto_resends(self):
        with patch(
            "apps.billing.fiscal_documents.EmailMessage.send", side_effect=TimeoutError
        ):
            deliver_documents(self.note.pk)
        deliver_documents(self.note.pk)
        self.assertEqual(FiscalInvoice.objects.get().delivery_status, "UNCERTAIN")
        self.assertEqual(len(mail.outbox), 0)

    def test_inflight_state_not_sent_twice(self):
        self.note.delivery_status = "SENDING"
        self.note.save()
        deliver_documents(self.note.pk)
        self.assertEqual(len(mail.outbox), 0)

    def test_wrong_environment_never_archives_or_sends(self):
        self.bill.environment = "production"
        self.bill.save()
        deliver_documents(self.note.pk)
        self.assertEqual(len(mail.outbox), 0)

    def test_document_failure_remains_pending_with_warning(self):
        with patch(
            "apps.billing.fiscal_documents.download_document", side_effect=ValueError
        ):
            deliver_documents(self.note.pk)
        self.note.refresh_from_db()
        self.assertEqual(self.note.delivery_status, "PENDING")
        self.assertTrue(self.note.delivery_notice)

    def owner(self):
        user = get_user_model().objects.create_user(
            username="doc-owner",
            password="test",
            tenant=self.tenant,
            is_staff=True,
            is_tenant_admin=True,
        )
        client = Client(HTTP_HOST="fiscal.lvh.me")
        client.force_login(user)
        return client

    def root(self):
        user = get_user_model().objects.create_superuser(
            username="doc-root", password="test", email="root@example.com"
        )
        client = Client(HTTP_HOST="localhost")
        client.force_login(user)
        return client

    def test_owner_history_and_private_download_after_link_expiry(self):
        deliver_documents(self.note.pk)
        FiscalInvoice.objects.filter(pk=self.note.pk).update(pdf_url="", xml_url="")
        client = self.owner()
        response = client.get(reverse("tenant_admin:billing_dashboard"))
        self.assertContains(response, "Nota fiscal")
        response = client.get(
            reverse("tenant_admin:billing_fiscal_download", args=[self.bill.pk, "pdf"])
        )
        self.assertEqual(response.content, PDF)
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("attachment;", response["Content-Disposition"])

    def test_anonymous_and_other_tenant_cannot_download(self):
        deliver_documents(self.note.pk)
        url = reverse(
            "tenant_admin:billing_fiscal_download", args=[self.bill.pk, "pdf"]
        )
        self.assertNotEqual(Client(HTTP_HOST="fiscal.lvh.me").get(url).status_code, 200)
        client = self.owner()
        from apps.tenants.models import Tenant

        other = Tenant.objects.create(
            name="Outro", slug="doc-other", whatsapp_number="5511999945511"
        )
        self.bill.tenant = other
        self.bill.save()
        self.assertEqual(client.get(url).status_code, 404)

    def test_superadmin_files_and_email_status(self):
        deliver_documents(self.note.pk)
        client = self.root()
        response = client.get(
            reverse("super_admin:billing_fiscalinvoice_change", args=[self.note.pk])
        )
        self.assertContains(response, "Documentos arquivados")
        response = client.get(
            reverse("super_admin:billing_nfse_download", args=[self.note.pk, "xml"])
        )
        self.assertEqual(response.content, XML)

    def test_csv_upload_original_bytes_download_superadmin_only(self):
        client = self.root()
        content = b"csv original;v004\r\n001;123\r\n"
        response = client.post(
            reverse("super_admin:billing_municipalexport_add"),
            {
                "month": str(self.rate.month),
                "environment": "sandbox",
                "upload": SimpleUploadedFile(
                    "prefeitura.csv", content, content_type="text/csv"
                ),
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 302)
        item = MunicipalExport.objects.get()
        self.assertEqual(bytes(item.content), content)
        url = reverse("super_admin:billing_csv_download", args=[item.pk])
        self.assertEqual(client.get(url).content, content)
        self.assertNotEqual(self.owner().get(url).status_code, 200)

    def test_hash_mismatch_denies_download(self):
        with self.assertRaises(Http404):
            attachment_response(PDF, "wrong", "note.pdf", "application/pdf")


class FiscalDownloaderTests(TestCase):
    @override_settings(NFSE_DOCUMENT_HOSTS=["docs.example.com"])
    def test_unapproved_host_and_private_ip_blocked(self):
        for url in [
            "http://docs.example.com/a",
            "https://evil.example/a",
            "https://user:pass@docs.example.com/a",
        ]:
            with self.assertRaises(ValueError):
                download_document(url, "pdf")
        with patch(
            "apps.billing.fiscal_documents.socket.getaddrinfo",
            return_value=[(0, 0, 0, 0, ("127.0.0.1", 443))],
        ):
            with self.assertRaises(ValueError):
                download_document("https://docs.example.com/a", "pdf")

    @override_settings(NFSE_DOCUMENT_HOSTS=["docs.example.com"])
    def test_pins_dns_validates_types_and_does_not_follow_redirects(self):
        with patch(
            "apps.billing.fiscal_documents.socket.getaddrinfo",
            return_value=[(0, 0, 0, 0, ("8.8.8.8", 443))],
        ), patch("apps.billing.fiscal_documents.urllib3.HTTPSConnectionPool") as pool:
            response = pool.return_value.urlopen.return_value
            response.status = 200
            response.stream.return_value = [PDF]
            self.assertEqual(
                download_document("https://docs.example.com/a", "pdf"), PDF
            )
            self.assertEqual(pool.call_args.args[0], "8.8.8.8")
            self.assertEqual(
                pool.call_args.kwargs["assert_hostname"], "docs.example.com"
            )
            self.assertFalse(pool.return_value.urlopen.call_args.kwargs["redirect"])
            for content, kind in [
                (b"<html>error</html>", "pdf"),
                (b"<!DOCTYPE a><a/>", "xml"),
                (b"x" * (LIMIT + 1), "pdf"),
            ]:
                response.stream.return_value = [content]
                with self.assertRaises(ValueError):
                    download_document("https://docs.example.com/a", kind)
            response.status = 302
            with self.assertRaises(ValueError):
                download_document("https://docs.example.com/a", "pdf")
