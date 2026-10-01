"""Regression tests for the manual WhatsApp -> Superadmin -> paid subscription funnel."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import signing
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.billing.models import Invoice
from apps.marketplace.acquisition import CLICK_SALT, link_lead, new_contact, record_click, record_first_payment
from apps.marketplace.models import MarketingLead, MarketingPaidConversion, MarketingMilestone
from apps.tenants.models import Tenant


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=[".vemdedelivery.com.br", "testserver"],
    MARKETING_PUBLIC_URL="https://vemdedelivery.com.br",
    MARKETING_LEAD_TRACKING_ENABLED=True,
    GOOGLE_TAG_MANAGER_ID="GTM-NGQGBHG9",
    BILLING_ENABLED=False,
)
class MarketingAcquisitionTests(TestCase):
    def request(self, url="/para-lojistas/"):
        r = RequestFactory().get(url, HTTP_HOST="vemdedelivery.com.br")
        r.tenant = None
        return r

    def test_signed_reference_only_created_on_actual_click_and_survives_no_js(self):
        from apps.marketplace.marketing_views import landing
        r = landing(self.request())
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Refer%C3%AAncia", r.content)
        self.assertIn(b"VDD-", r.content)
        self.assertEqual(MarketingLead.objects.count(), 0)
        contact = new_contact(self.request())
        self.assertIn("VDD-", contact["url"])
        lead, created = record_click(token=contact["token"], cta="hero", consent=False,
                                     attribution={"gclid": "ineligible", "utm_source": "google", "ga_client_id": "123.456"})
        self.assertTrue(created)
        self.assertEqual(lead.reference, contact["reference"])
        self.assertFalse(lead.analytics_consent)
        self.assertEqual(lead.gclid, "")
        self.assertEqual(lead.ga_client_id, "")
        _, created2 = record_click(token=contact["token"], cta="footer", consent=True,
                                   attribution={"gclid": "lateclick", "utm_source": "google"})
        self.assertFalse(created2)
        lead.refresh_from_db()
        self.assertEqual(lead.gclid, "")
        self.assertEqual(lead.cta, "hero")

    def test_opt_in_attribution_and_expired_or_invalid_token(self):
        contact = new_contact(self.request())
        lead, _ = record_click(token=contact["token"], cta="seo_hero", consent=True,
                               attribution={"utm_campaign": "campA", "gclid": "abc123", "ga_client_id": "12345.67890"})
        self.assertEqual(lead.utm_campaign, "campA")
        self.assertEqual(lead.gclid, "abc123")
        self.assertEqual(lead.ga_client_id, "12345.67890")
        with self.assertRaises(signing.BadSignature):
            record_click(token=contact["token"] + "corrupt", cta="x", consent=False, attribution={})

    def test_csrf_and_canonical_host_protect_click_endpoint(self):
        client = Client(enforce_csrf_checks=True)
        url = "/marketing/registrar-clique/"
        token = new_contact(self.request())["token"]
        payload = {"token": token, "cta": "header", "consent": "no"}
        self.assertEqual(client.post(url, payload, HTTP_HOST="vemdedelivery.com.br").status_code, 403)
        client.get("/para-lojistas/", HTTP_HOST="vemdedelivery.com.br")
        csrftoken = client.cookies["csrftoken"].value
        result = client.post(url, {**payload, "csrfmiddlewaretoken": csrftoken}, HTTP_HOST="vemdedelivery.com.br")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(MarketingLead.objects.count(), 1)
        self.assertEqual(client.post(url, {**payload, "csrfmiddlewaretoken": csrftoken}, HTTP_HOST="homolog.vemdedelivery.com.br").status_code, 404)

    def test_manual_link_and_exactly_one_paid_acquisition(self):
        tenant = Tenant.objects.create(name="Cliente", slug="cliente-acq", whatsapp_number="5511987654401")
        contact = new_contact(self.request())
        lead, _ = record_click(token=contact["token"], cta="hero", consent=True,
                               attribution={"utm_source": "google", "ga_client_id": "123.456"})
        link_lead(tenant, lead.reference)
        self.assertEqual(MarketingLead.objects.get(pk=lead.pk).tenant, tenant)
        self.assertFalse(MarketingPaidConversion.objects.exists())
        self.assertTrue(MarketingMilestone.objects.filter(lead=lead, name="signup_completed").exists())
        def invoice(*, months=1, status="PAID", environment="production", amount="149.00"):
            return Invoice.objects.create(
                tenant=tenant, plan_name="Mensal", months=months, amount=Decimal(amount),
                method="PIX", environment=environment, status=status, paid_at=timezone.now(),
                due_date=timezone.localdate() + timedelta(days=5),
            )
        with patch("requests.post") as request:
            with self.captureOnCommitCallbacks(execute=True):
                invoice(status="PENDING")  # No payment: no conversion.
                invoice(months=0)  # Additional/manual zero-month: no acquisition.
                paid = invoice()
            self.assertEqual(MarketingPaidConversion.objects.count(), 1)
            self.assertEqual(MarketingPaidConversion.objects.get().invoice_id, paid.pk)
            self.assertTrue(MarketingMilestone.objects.filter(lead=lead, name="subscription_created").exists())
            with self.captureOnCommitCallbacks(execute=True):
                invoice()  # Renewal: never another first acquisition.
            self.assertEqual(MarketingPaidConversion.objects.count(), 1)
            record_first_payment(paid)
            self.assertEqual(MarketingPaidConversion.objects.count(), 1)
            request.assert_not_called()  # Nothing external from billing/webhook.

    def test_paid_before_admin_links_lead_is_reconciled(self):
        tenant = Tenant.objects.create(name="Cliente", slug="cliente-acq2", whatsapp_number="5511987654402")
        paid = Invoice.objects.create(
            tenant=tenant, plan_name="Mensal", months=1, amount=Decimal("149.00"),
            method="PIX", environment="production", status="PAID",
            paid_at=timezone.now(), due_date=timezone.localdate(),
        )
        self.assertEqual(MarketingPaidConversion.objects.count(), 0)
        ref = new_contact(self.request())["reference"]
        link_lead(tenant, ref)
        conv = MarketingPaidConversion.objects.get()
        self.assertEqual(conv.invoice_id, paid.pk)
        self.assertEqual(conv.lead.source_note, "manual_unverified")

    @override_settings(MARKETING_LEAD_TRACKING_ENABLED=False)
    def test_feature_flag_off_does_not_change_whatsapp_links(self):
        from apps.marketplace.marketing_views import landing
        body = landing(self.request()).content.decode()
        self.assertIn("https://wa.me/", body)
        self.assertNotIn("Refer%C3%AAncia", body)
        self.assertEqual(MarketingLead.objects.count(), 0)

    def test_admin_create_and_change_forms_expose_reference(self):
        from apps.tenants.admin import TenantAdmin
        from apps.tenants.admin_site import super_admin_site
        admin = TenantAdmin(Tenant, super_admin_site)
        request = self.request("/superadmin/tenants/tenant/add/")
        from django.contrib.auth import get_user_model
        request.user = get_user_model().objects.create_superuser(
            username="super-marketing", email="super-marketing@example.com", password="test-12345"
        )
        form = admin.get_form(request, obj=None)
        self.assertIn("marketing_lead_reference", form.base_fields)
        tenant = Tenant.objects.create(name="Cliente", slug="cliente-acq3", whatsapp_number="5511987654403")
        change = admin.get_form(request, obj=tenant)
        self.assertIn("marketing_lead_reference", change.base_fields)

    def test_ga4_dispatch_only_consented_milestones_and_payment_is_idempotent(self):
        from apps.marketplace.models import MarketingMilestone
        tenant = Tenant.objects.create(name="Cliente", slug="cliente-acq4", whatsapp_number="5511987654404")
        contact = new_contact(self.request())
        lead, _ = record_click(token=contact["token"], cta="hero", consent=True,
                               attribution={"ga_client_id": "123.456", "utm_source": "google"})
        link_lead(tenant, lead.reference)
        with self.captureOnCommitCallbacks(execute=True):
            Invoice.objects.create(
                tenant=tenant, plan_name="Mensal", months=1, amount=Decimal("149.00"),
                method="PIX", environment="production", status="PAID",
                paid_at=timezone.now(), due_date=timezone.localdate(),
            )
        with override_settings(MARKETING_GA4_MEASUREMENT_ID="G-test", MARKETING_GA4_API_SECRET="unit-only"):
            with patch("apps.marketplace.management.commands.send_marketing_conversions.requests.post") as post:
                post.return_value.status_code = 204
                post.return_value.raise_for_status.return_value = None
                call_command("send_marketing_conversions")
                self.assertEqual(post.call_count, 3)
                events = [call.kwargs["json"]["events"][0]["name"] for call in post.call_args_list]
                self.assertEqual(set(events), {"signup_completed", "subscription_created", "subscription_paid"})
                call_command("send_marketing_conversions")
                self.assertEqual(post.call_count, 3)
        self.assertEqual(MarketingMilestone.objects.filter(ga4_sent_at__isnull=False).count(), 2)
        self.assertEqual(MarketingPaidConversion.objects.filter(ga4_sent_at__isnull=False).count(), 1)

    def test_payment_review_blocks_ads_export_without_touching_billing(self):
        from io import StringIO
        tenant = Tenant.objects.create(name="Cliente", slug="cliente-acq5", whatsapp_number="5511987654405")
        contact = new_contact(self.request())
        lead, _ = record_click(token=contact["token"], cta="plan", consent=True,
                               attribution={"ga_client_id": "123.456", "gclid": "consented-id"})
        link_lead(tenant, lead.reference)
        with self.captureOnCommitCallbacks(execute=True):
            bill = Invoice.objects.create(tenant=tenant, plan_name="Mensal", months=1,
                amount=Decimal("149.00"), method="PIX", environment="production",
                status="PAID", paid_at=timezone.now(), due_date=timezone.localdate())
        self.assertEqual(MarketingPaidConversion.objects.count(), 1)
        bill.status = "REVIEW"
        with self.captureOnCommitCallbacks(execute=True):
            bill.save(update_fields=["status"])
        self.assertIsNotNone(MarketingPaidConversion.objects.get().retracted_at)
        output = StringIO()
        call_command("export_marketing_ads", stdout=output)
        self.assertNotIn("consented-id", output.getvalue())
