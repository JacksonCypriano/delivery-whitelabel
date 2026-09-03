import uuid
from datetime import timedelta, date
from decimal import Decimal
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.billing.models import (
    Invoice,
    FiscalInvoice,
    FiscalSettings,
    TaxRate,
    BillingEvent,
    BillingCustomer,
    FiscalCustomerRule,
)
from apps.billing.fiscal import (
    process_fiscal,
    payment_day,
    document_url,
    monthly_warning,
)
from apps.billing.fiscal_models import fiscal_today
from apps.billing.provider import ProviderUnavailable, BillingError
from apps.billing.tasks import process_event, reconcile_fiscal_invoices


@override_settings(
    BILLING_ENABLED=True,
    ASAAS_ENVIRONMENT="sandbox",
    ASAAS_API_KEY="test-only",
    ASAAS_WEBHOOK_TOKEN="testing-token-longer-than-thirty-two-characters",
)
class FiscalTests(TestCase):
    def setUp(self):
        enqueue = patch('apps.billing.tasks.archive_and_send_nfse.delay')
        enqueue.start()
        self.addCleanup(enqueue.stop)
        self.tenant = Tenant.objects.create(
            name="Fiscal", slug="fiscal", whatsapp_number="5511999994411"
        )
        self.bill = Invoice.objects.create(
            tenant=self.tenant,
            plan_name="Mensal",
            months=1,
            amount=199,
            method="PIX",
            environment="sandbox",
            provider_id="pay_fiscal",
            customer_id_external="cus_fiscal",
            status="PAID",
            due_date=fiscal_today(),
            paid_at=timezone.now(),
        )
        self.config = FiscalSettings.objects.create(
            environment="sandbox",
            enabled=True,
            start_at=timezone.now() - timedelta(days=1),
            service_code="02692",
        )
        self.rate = TaxRate.objects.create(
            configuration=self.config,
            month=fiscal_today().replace(day=1),
            iss="2.01",
            checked_at=timezone.now(),
        )
        self.api = Mock()
        self.api.get_payment.return_value = self.payment()
        self.api.request.side_effect = self.request
        patcher = patch("apps.billing.fiscal.Asaas", return_value=self.api)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.posts = []
        self.remote = []

    def payment(self):
        return {
            "id": self.bill.provider_id,
            "customer": "cus_fiscal",
            "externalReference": self.bill.reference,
            "billingType": "PIX",
            "value": 199,
            "status": "RECEIVED",
            "paymentDate": str(fiscal_today()),
        }

    def request(self, method, path, **kwargs):
        if method == "POST":
            body = kwargs["json"]
            self.posts.append(body)
            result = dict(
                body,
                id="inv_fiscal",
                customer="cus_fiscal",
                status="AUTHORIZED",
                number="123",
                pdfUrl="https://example.com/nota.pdf",
            )
            self.remote = [result]
            return result
        if path == "/invoices":
            return {"data": self.remote, "hasMore": False}
        return self.remote[0]

    def test_paid_issues_once_and_keeps_gross_value(self):
        process_fiscal(self.bill.pk)
        process_fiscal(self.bill.pk)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.posts[0]["value"], 199)
        self.assertFalse(self.posts[0]["updatePayment"])
        self.assertEqual(self.posts[0]["taxes"]["iss"], 2.01)
        self.assertEqual(FiscalInvoice.objects.get().status, "AUTHORIZED")

    def test_pending_pix_never_issues(self):
        self.bill.status = "PENDING"
        self.bill.save()
        process_fiscal(self.bill.pk)
        self.assertFalse(FiscalInvoice.objects.exists())
        self.assertFalse(self.posts)

    def test_disabled_fiscal_does_nothing(self):
        self.config.enabled = False
        self.config.save()
        process_fiscal(self.bill.pk)
        self.api.get_payment.assert_not_called()

    def test_environment_isolation(self):
        self.bill.environment = "production"
        self.bill.save()
        process_fiscal(self.bill.pk)
        self.assertFalse(FiscalInvoice.objects.exists())

    def test_old_payment_is_not_imported(self):
        self.bill.paid_at = self.config.start_at - timedelta(days=1)
        self.bill.save()
        process_fiscal(self.bill.pk)
        self.assertFalse(FiscalInvoice.objects.exists())

    def test_missing_month_blocks_note_not_subscription(self):
        self.rate.delete()
        process_fiscal(self.bill.pk)
        note = FiscalInvoice.objects.get()
        self.assertIn("alíquota", note.notice)
        self.assertFalse(note.attempted)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, "PAID")

    def test_confirmation_month_used_not_worker_month(self):
        prior = fiscal_today().replace(day=1) - timedelta(days=1)
        self.config.start_at = timezone.now() - timedelta(days=70)
        self.config.save()
        TaxRate.objects.create(
            configuration=self.config,
            month=prior.replace(day=1),
            iss="2.50",
            checked_at=timezone.now(),
        )
        self.api.get_payment.return_value = dict(self.payment(), paymentDate=str(prior))
        process_fiscal(self.bill.pk)
        self.assertEqual(self.posts[0]["effectiveDate"], str(prior))
        self.assertEqual(self.posts[0]["taxes"]["iss"], 2.5)

    def test_missing_payment_date_does_not_use_today(self):
        self.api.get_payment.return_value = dict(self.payment(), paymentDate=None)
        process_fiscal(self.bill.pk)
        self.assertFalse(self.posts)
        self.assertIn("Data de confirmação", FiscalInvoice.objects.get().notice)

    def test_timeout_never_reposts(self):
        def fail(method, path, **kwargs):
            if method == "POST":
                self.posts.append(kwargs["json"])
                raise ProviderUnavailable("Timeout")
            return {"data": [], "hasMore": False}

        self.api.request.side_effect = fail
        process_fiscal(self.bill.pk)
        process_fiscal(self.bill.pk)
        self.assertEqual(len(self.posts), 1)
        self.assertTrue(FiscalInvoice.objects.get().attempted)

    def test_timeout_recovers_remote_note(self):
        def fail(method, path, **kwargs):
            result = self.request(method, path, **kwargs)
            if method == "POST":
                raise ProviderUnavailable("Timeout")
            return result

        self.api.request.side_effect = fail
        process_fiscal(self.bill.pk)
        process_fiscal(self.bill.pk)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(FiscalInvoice.objects.get().status, "AUTHORIZED")

    def test_manual_remote_note_blocks_duplicate(self):
        self.remote = [{"id": "inv_manual"}]
        process_fiscal(self.bill.pk)
        self.assertFalse(self.posts)
        self.assertIn("Já existe", FiscalInvoice.objects.get().notice)

    def test_divergent_payment_blocks_emission(self):
        for key, value in [
            ("value", 1),
            ("customer", "cus_other"),
            ("externalReference", "other"),
        ]:
            self.api.get_payment.return_value = dict(self.payment(), **{key: value})
            process_fiscal(self.bill.pk)
            self.assertFalse(self.posts)

    def test_refund_holds_note(self):
        self.api.get_payment.return_value = dict(self.payment(), status="REFUNDED")
        process_fiscal(self.bill.pk)
        self.assertTrue(FiscalInvoice.objects.get().review_required)
        self.assertFalse(self.posts)

    def test_refund_after_authorization_never_cancels_automatically(self):
        process_fiscal(self.bill.pk)
        self.bill.status = "REVIEW"
        self.bill.save()
        process_fiscal(self.bill.pk)
        self.assertTrue(FiscalInvoice.objects.get().review_required)
        self.assertEqual(len(self.posts), 1)

    def test_rate_snapshot_unchanged_after_rate_edit(self):
        process_fiscal(self.bill.pk)
        self.rate.iss = 3
        self.rate.save()
        process_fiscal(self.bill.pk)
        self.assertEqual(FiscalInvoice.objects.get().iss, Decimal("2.01"))

    def test_customer_exception_hold_and_retention(self):
        customer = BillingCustomer.objects.create(
            tenant=self.tenant,
            environment="sandbox",
            name="Pagador",
            document="123",
            email="test@example.com",
        )
        rule = FiscalCustomerRule.objects.create(
            customer=customer,
            hold=True,
            retain_iss=True,
            reason="Orientação do contador",
        )
        process_fiscal(self.bill.pk)
        self.assertFalse(self.posts)
        rule.hold = False
        rule.save()
        process_fiscal(self.bill.pk)
        self.assertTrue(self.posts[0]["taxes"]["retainIss"])

    def test_monthly_warning_and_dates(self):
        self.assertIn("Última conferência", monthly_warning(self.config))
        self.rate.delete()
        self.assertIn("ATENÇÃO", monthly_warning(self.config))
        with self.assertRaises(ValidationError):
            TaxRate(
                configuration=self.config, month=date(2099, 1, 1), iss=2
            ).full_clean()
        with self.assertRaises(ValidationError):
            TaxRate(
                configuration=self.config, month=date(2026, 1, 2), iss=2
            ).full_clean()

    def test_document_url_rejects_unsafe_schemes(self):
        for value in [
            "javascript:alert(1)",
            "http://example.com/x",
            "https://user:pass@example.com/x",
            "https://example.com:444/x",
            None,
        ]:
            self.assertEqual(document_url(value), "")

    def test_webhook_invoice_persisted_and_duplicate_idempotent(self):
        client = Client(HTTP_HOST="localhost")
        payload = {
            "id": "evt_fiscal",
            "event": "INVOICE_AUTHORIZED",
            "invoice": {"id": "inv_fiscal"},
        }
        for _ in range(2):
            response = client.post(
                "/integracoes/asaas/webhook/",
                data=payload,
                content_type="application/json",
                HTTP_ASAAS_ACCESS_TOKEN="testing-token-longer-than-thirty-two-characters",
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(BillingEvent.objects.count(), 1)

    def test_tenant_cannot_access_other_tenant_note_or_fiscal_admin(self):
        other = Tenant.objects.create(
            name="Outra", slug="outra-fiscal", whatsapp_number="5511999994412"
        )
        user = get_user_model().objects.create_user(
            username="other-fiscal",
            password="test",
            is_staff=True,
            is_tenant_admin=True,
            tenant=other,
        )
        client = Client(HTTP_HOST="outra-fiscal.lvh.me")
        client.force_login(user)
        response = client.get(
            reverse("tenant_admin:billing_invoice", args=[self.bill.pk])
        )
        self.assertEqual(response.status_code, 404)
        response = client.get(reverse("super_admin:billing_taxrate_changelist"))
        self.assertNotEqual(response.status_code, 200)

    def test_owner_can_read_own_note(self):
        process_fiscal(self.bill.pk)
        user = get_user_model().objects.create_user(
            username="owner-fiscal",
            password="test",
            is_staff=True,
            is_tenant_admin=True,
            tenant=self.tenant,
        )
        client = Client(HTTP_HOST="fiscal.lvh.me")
        client.force_login(user)
        response = client.get(
            reverse("tenant_admin:billing_invoice", args=[self.bill.pk])
        )
        self.assertContains(response, "PDF aguardando autorização ou arquivamento")

    def test_fiscal_queue_creates_and_processes(self):
        reconcile_fiscal_invoices()
        self.assertEqual(FiscalInvoice.objects.get().status, "AUTHORIZED")

    def test_remote_divergence_does_not_authorize(self):
        def changed(method, path, **kwargs):
            result = self.request(method, path, **kwargs)
            if method == "POST":
                result["customer"] = "cus_other"
            return result

        self.api.request.side_effect = changed
        process_fiscal(self.bill.pk)
        self.assertEqual(FiscalInvoice.objects.get().status, "UNCERTAIN")
        self.assertIn("divergente", FiscalInvoice.objects.get().notice)

    def test_webhook_reconciles_using_authenticated_api(self):
        process_fiscal(self.bill.pk)
        event = BillingEvent.objects.create(
            event_id="sandbox:evt_ok",
            payment_id="inv_fiscal",
            kind="INVOICE_AUTHORIZED",
            environment="sandbox",
        )
        with patch("apps.billing.tasks.Asaas", return_value=self.api):
            process_event(event.pk)
        event.refresh_from_db()
        self.assertIsNotNone(event.processed_at)

    def test_disabled_fiscal_preserves_webhook_for_retry(self):
        process_fiscal(self.bill.pk)
        self.config.enabled = False
        self.config.save()
        event = BillingEvent.objects.create(
            event_id="sandbox:evt_disabled",
            payment_id="inv_fiscal",
            kind="INVOICE_AUTHORIZED",
            environment="sandbox",
        )
        with patch("apps.billing.tasks.Asaas", return_value=self.api):
            process_event(event.pk)
        event.refresh_from_db()
        self.assertIsNone(event.processed_at)

    def test_superadmin_warning_and_conference_audit(self):
        root = get_user_model().objects.create_superuser(
            username="fiscal-root", email="fiscal@example.com", password="test"
        )
        client = Client(HTTP_HOST="localhost")
        client.force_login(root)
        response = client.get(
            reverse("super_admin:billing_taxrate_change", args=[self.rate.pk])
        )
        self.assertContains(response, "CADA MÊS")
        response = client.post(
            reverse("super_admin:billing_taxrate_change", args=[self.rate.pk]),
            {
                "configuration": self.config.pk,
                "month": str(self.rate.month),
                "iss": "2.03",
                "_save": "Salvar",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.rate.refresh_from_db()
        self.assertEqual(self.rate.checked_by, root)
        self.assertEqual(self.rate.iss, Decimal("2.03"))

    def test_webhook_rejects_wrong_auth(self):
        response = Client(HTTP_HOST="localhost").post(
            "/integracoes/asaas/webhook/",
            data={"id": "evt_bad"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
