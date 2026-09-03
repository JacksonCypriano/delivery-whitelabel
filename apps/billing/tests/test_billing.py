import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, Mock
from django.conf import settings
from django.core import signing
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.billing.models import (
    Subscription,
    Plan,
    BillingSettings,
    Invoice,
    Credit,
    BillingEvent,
    BillingAudit,
    BillingCustomer,
)
from apps.billing.services import (
    apply_payment,
    suspend_due,
    manual_credit,
    price_for,
    reserve_invoice,
    issue_invoice,
    reconcile_invoice,
)
from apps.billing.provider import BillingError, ProviderUnavailable, Asaas, payment_url

OPTIONS = {
    "BILLING_ENABLED": True,
    "ASAAS_ENVIRONMENT": "sandbox",
    "ASAAS_API_KEY": "test-key",
    "ASAAS_WEBHOOK_TOKEN": "test-webhook-token-with-more-than-32-characters",
}


class BillingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja Assinante", slug="assinante", whatsapp_number="5511988880001"
        )
        self.sub = self.tenant.subscription
        self.plan = Plan.objects.get(months=1)
        self.user = get_user_model().objects.create_user(
            username="billing-owner",
            password="Senha!123",
            is_staff=True,
            is_tenant_admin=True,
            tenant=self.tenant,
        )
        self.root = get_user_model().objects.create_superuser(
            username="billing-root", password="Senha!123", email="root@example.com"
        )
        self.client = Client(HTTP_HOST="assinante.lvh.me")
        self.client.force_login(self.user)

    def bill(self, months=1, method="PIX", **extra):
        return Invoice.objects.create(
            tenant=self.tenant,
            plan_name="Teste",
            months=months,
            method=method,
            amount=Decimal("199"),
            environment="sandbox",
            provider_id="pay_" + uuid.uuid4().hex,
            customer_id_external="cus_123",
            due_date=timezone.localdate() + timedelta(days=2),
            **extra,
        )

    def paid(self, bill, **extra):
        return {
            "id": bill.provider_id,
            "externalReference": bill.reference,
            "customer": "cus_123",
            "billingType": bill.method,
            "value": 199,
            "status": "RECEIVED",
            **extra,
        }

    def test_plans_and_disabled_methods(self):
        self.assertEqual(
            [p.price for p in Plan.objects.all()],
            [Decimal("199"), Decimal("567.15"), Decimal("1074.60"), Decimal("2029.80")],
        )
        for method in ("BOLETO", "CREDIT_CARD"):
            with self.assertRaises(BillingError):
                price_for(self.plan, method)
        p = BillingSettings.current()
        p.card_enabled = True
        p.save()
        self.assertEqual(price_for(self.plan, "CREDIT_CARD"), Decimal("203.59"))

    def test_installation_does_not_suspend_existing(self):
        self.assertFalse(self.sub.managed)
        self.assertEqual(suspend_due(), 0)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.is_active)

    @override_settings(**OPTIONS)
    def test_new_store_starts_suspended_with_admin_access(self):
        t = Tenant.objects.create(
            name="Nova", slug="nova", whatsapp_number="5511988880002"
        )
        self.assertFalse(t.is_active)
        self.assertTrue(t.subscription.managed)
        self.assertTrue(t.subscription.billing_suspended)

    @override_settings(**OPTIONS)
    def test_paid_accumulates_and_webhooks_are_idempotent(self):
        with patch(
            "apps.billing.services.timezone.localdate", return_value=date(2026, 1, 31)
        ):
            first = self.bill()
            apply_payment(first.pk, self.paid(first))
            second = self.bill(months=6)
            apply_payment(second.pk, self.paid(second))
            apply_payment(first.pk, self.paid(first))
            apply_payment(second.pk, self.paid(second, status="PENDING"))
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.valid_until, date(2026, 8, 31))
        self.assertEqual(Credit.objects.count(), 2)
        second.refresh_from_db()
        self.assertEqual(second.status, "PAID")

    @override_settings(**OPTIONS)
    def test_expired_starts_today_and_reactivates(self):
        self.sub.managed = True
        self.sub.valid_until = date(2025, 1, 1)
        self.sub.billing_suspended = True
        self.sub.save()
        Tenant.objects.filter(pk=self.tenant.pk).update(is_active=False)
        b = self.bill(months=3)
        with patch(
            "apps.billing.services.timezone.localdate", return_value=date(2026, 9, 3)
        ):
            apply_payment(b.pk, self.paid(b))
        self.sub.refresh_from_db()
        self.tenant.refresh_from_db()
        self.assertEqual(self.sub.valid_until, date(2026, 12, 3))
        self.assertTrue(self.tenant.is_active)

    @override_settings(**OPTIONS)
    def test_grace_boundary_daily_and_payment_not_suspended(self):
        self.sub.managed = True
        self.sub.valid_until = date(2026, 9, 10)
        self.sub.save()
        self.assertEqual(suspend_due(date(2026, 9, 12)), 0)
        self.assertEqual(suspend_due(date(2026, 9, 13)), 1)
        self.assertEqual(suspend_due(date(2026, 9, 13)), 0)
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.is_active)
        b = self.bill()
        with patch(
            "apps.billing.services.timezone.localdate", return_value=date(2026, 9, 13)
        ):
            apply_payment(b.pk, self.paid(b))
            self.assertEqual(suspend_due(date(2026, 9, 13)), 0)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.is_active)

    @override_settings(**OPTIONS)
    def test_manual_block_survives_payment(self):
        self.sub.manually_blocked = True
        self.sub.billing_suspended = True
        self.sub.save()
        b = self.bill()
        apply_payment(b.pk, self.paid(b))
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.is_active)
        self.assertEqual(Credit.objects.count(), 1)

    @override_settings(**OPTIONS)
    def test_mismatch_and_pix_confirmed_do_not_credit(self):
        b = self.bill()
        for extra in [
            {"value": 1},
            {"customer": "cus_other"},
            {"externalReference": "other"},
            {"billingType": "CREDIT_CARD"},
            {"id": "pay_other"},
        ]:
            with self.assertRaises(BillingError):
                apply_payment(b.pk, self.paid(b, **extra))
        apply_payment(b.pk, self.paid(b, status="CONFIRMED"))
        self.assertEqual(Credit.objects.count(), 0)

    @override_settings(**OPTIONS)
    def test_credit_confirmed_can_grant_once_before_settlement(self):
        b = self.bill(method="CREDIT_CARD")
        apply_payment(b.pk, self.paid(b, status="CONFIRMED"))
        apply_payment(b.pk, self.paid(b))
        self.assertEqual(Credit.objects.count(), 1)

    @override_settings(**OPTIONS)
    def test_refund_blocks_and_out_of_order_paid_cannot_unblock(self):
        b = self.bill()
        apply_payment(b.pk, self.paid(b))
        apply_payment(b.pk, self.paid(b, status="REFUNDED"))
        apply_payment(b.pk, self.paid(b))
        self.sub.refresh_from_db()
        self.tenant.refresh_from_db()
        b.refresh_from_db()
        self.assertTrue(self.sub.payment_review)
        self.assertFalse(self.tenant.is_active)
        self.assertEqual(b.status, "REVIEW")
        self.assertEqual(Credit.objects.count(), 1)

    def test_manual_credit_permissions_and_duplicate(self):
        token = uuid.uuid4()
        with self.assertRaises(BillingError):
            manual_credit(self.tenant, 1, "Pix conferido", self.user, token)
        manual_credit(self.tenant, 1, "Pix externo conferido", self.root, token)
        manual_credit(self.tenant, 1, "Pix externo conferido", self.root, token)
        self.assertEqual(Credit.objects.count(), 1)

    def test_inactive_owner_can_access_billing_but_other_store_cannot(self):
        Tenant.objects.filter(pk=self.tenant.pk).update(is_active=False)
        r = self.client.get("/admin/minha-assinatura/")
        self.assertEqual(r.status_code, 200)
        b = self.bill()
        t = Tenant.objects.create(
            name="Outra", slug="outra", whatsapp_number="5511988880003"
        )
        other = get_user_model().objects.create_user(
            username="other-owner", is_staff=True, is_tenant_admin=True, tenant=t
        )
        self.client.force_login(other)
        self.assertEqual(
            self.client.get(
                f"/admin/minha-assinatura/cobranca/{b.pk}/", HTTP_HOST="outra.lvh.me"
            ).status_code,
            404,
        )

    def test_anonymous_customer_and_csrf_cannot_purchase(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST="assinante.lvh.me")
        self.assertEqual(client.get("/admin/minha-assinatura/").status_code, 302)
        client.force_login(self.user)
        self.assertEqual(
            client.post("/admin/minha-assinatura/comprar/", {}).status_code, 403
        )
        self.assertEqual(Invoice.objects.count(), 0)

    @override_settings(**OPTIONS)
    def test_signed_price_disabled_method_and_double_click(self):
        token = uuid.uuid4()
        args = [
            self.tenant,
            self.plan,
            "PIX",
            Decimal("199"),
            token,
            "Pagador",
            "12345678909",
            "a@example.com",
        ]
        b = reserve_invoice(*args)
        same = reserve_invoice(*args)
        self.assertEqual(b.pk, same.pk)
        args[4] = uuid.uuid4()
        self.assertEqual(reserve_invoice(*args).pk, b.pk)
        args[2] = "CREDIT_CARD"
        args[4] = uuid.uuid4()
        with self.assertRaises(BillingError):
            reserve_invoice(*args)
        self.assertEqual(Invoice.objects.count(), 1)

    @override_settings(**OPTIONS)
    def test_creation_timeout_is_not_reposted_and_recovers(self):
        token = uuid.uuid4()
        b = reserve_invoice(
            self.tenant,
            self.plan,
            "PIX",
            Decimal("199"),
            token,
            "Teste",
            "12345678909",
            "t@example.com",
        )
        BillingCustomer.objects.filter(tenant=self.tenant).update(provider_id="cus_123")
        with patch(
            "apps.billing.services.Asaas.create_payment",
            side_effect=ProviderUnavailable("Timeout"),
        ) as create:
            with self.assertRaises(ProviderUnavailable):
                issue_invoice(b.pk)
            issue_invoice(b.pk)
            self.assertEqual(create.call_count, 1)
        b.refresh_from_db()
        self.assertEqual(b.status, "UNCERTAIN")
        payment = self.paid(b, id="pay_recovered")
        with patch(
            "apps.billing.services.Asaas.find_payment", return_value={"data": [payment]}
        ):
            reconcile_invoice(b.pk)
        self.assertEqual(Credit.objects.count(), 1)

    @override_settings(**OPTIONS)
    def test_webhook_auth_persistence_duplicate_and_worker(self):
        b = self.bill()
        payload = {
            "id": "evt123",
            "event": "PAYMENT_RECEIVED",
            "payment": {"id": b.provider_id, "value": 1},
        }
        url = "/integracoes/asaas/webhook/"
        self.assertEqual(
            self.client.post(
                url, json.dumps(payload), content_type="application/json"
            ).status_code,
            403,
        )
        with patch(
            "apps.billing.tasks.process_event.delay",
            side_effect=RuntimeError("broker down"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                for _ in range(2):
                    self.assertEqual(
                        self.client.post(
                            url,
                            json.dumps(payload),
                            content_type="application/json",
                            HTTP_ASAAS_ACCESS_TOKEN=OPTIONS["ASAAS_WEBHOOK_TOKEN"],
                        ).status_code,
                        200,
                    )
        self.assertEqual(BillingEvent.objects.count(), 1)
        self.assertEqual(Credit.objects.count(), 0)
        from apps.billing.tasks import process_event

        with patch("apps.billing.tasks.Asaas.get_payment", return_value=self.paid(b)):
            process_event(BillingEvent.objects.get().pk)
        self.assertEqual(Credit.objects.count(), 1)

    def test_urls_only_allow_provider_https_and_daily_timezone(self):
        for url in [
            "javascript:alert(1)",
            "https://evil.test/",
            "http://sandbox.asaas.com/i/1",
            "https://sandbox.asaas.com.evil.test/i/1",
        ]:
            self.assertEqual(payment_url(url), "")
        self.assertEqual(
            payment_url("https://sandbox.asaas.com/i/1"),
            "https://sandbox.asaas.com/i/1",
        )
        self.assertEqual(settings.CELERY_TIMEZONE, "America/Sao_Paulo")
        schedule = settings.CELERY_BEAT_SCHEDULE["billing-suspend-daily"]["schedule"]
        self.assertEqual(schedule.hour, {6})
        self.assertEqual(schedule.minute, {0})

    def test_admin_notice_and_superadmin_history_readonly(self):
        self.sub.managed = True
        self.sub.valid_until = timezone.localdate() + timedelta(days=3)
        self.sub.save()
        response = self.client.get("/admin/")
        self.assertContains(response, "Ver assinatura e renovar")
        root_client = Client(HTTP_HOST="vemdedelivery.com.br")
        root_client.force_login(self.root)
        self.assertEqual(
            root_client.get("/superadmin/billing/subscription/").status_code, 200
        )
        self.assertEqual(
            root_client.post("/superadmin/billing/credit/add/", {}).status_code, 403
        )

    @override_settings(**OPTIONS)
    def test_rejected_customer_can_be_corrected_without_duplicate_payment(self):
        from apps.billing.provider import ProviderRejected

        b = reserve_invoice(
            self.tenant,
            self.plan,
            "PIX",
            Decimal("199"),
            uuid.uuid4(),
            "Teste",
            "11111111111",
            "t@example.com",
        )
        with patch(
            "apps.billing.services.Asaas.find_customer", return_value={"data": []}
        ), patch(
            "apps.billing.services.Asaas.create_customer",
            side_effect=ProviderRejected("Dados recusados"),
        ):
            with self.assertRaises(ProviderRejected):
                issue_invoice(b.pk)
        b.refresh_from_db()
        self.assertEqual(b.status, "ERROR")
        customer = BillingCustomer.objects.get(tenant=self.tenant)
        self.assertFalse(customer.attempted)
        reserve_invoice(
            self.tenant,
            self.plan,
            "PIX",
            Decimal("199"),
            uuid.uuid4(),
            "Teste",
            "12345678909",
            "t@example.com",
        )
        customer.refresh_from_db()
        self.assertEqual(customer.document, "12345678909")

    @override_settings(**OPTIONS)
    def test_partial_refund_is_held_for_review(self):
        b = self.bill()
        apply_payment(b.pk, self.paid(b))
        apply_payment(b.pk, self.paid(b, refunds=[{"value": 10}]))
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.is_active)
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.payment_review)

    @override_settings(**OPTIONS)
    def test_quote_tampering_cannot_create_invoice(self):
        data = {
            "quote": "tampered",
            "name": "Pagador",
            "document": "12345678909",
            "email": "x@example.com",
        }
        self.assertEqual(
            self.client.post("/admin/minha-assinatura/comprar/", data).status_code, 302
        )
        self.assertEqual(Invoice.objects.count(), 0)

    @override_settings(**OPTIONS)
    def test_issue_payload_pix_customer_notifications_off(self):
        b = reserve_invoice(
            self.tenant,
            self.plan,
            "PIX",
            Decimal("199"),
            uuid.uuid4(),
            "Pagador",
            "12345678909",
            "x@example.com",
        )
        with patch(
            "apps.billing.services.Asaas.find_customer", return_value={"data": []}
        ), patch(
            "apps.billing.services.Asaas.create_customer",
            return_value={"id": "cus_123"},
        ) as customer, patch(
            "apps.billing.services.Asaas.create_payment",
            return_value={
                "id": "pay_new",
                "invoiceUrl": "https://sandbox.asaas.com/i/new",
            },
        ) as payment:
            issue_invoice(b.pk)
        self.assertTrue(customer.call_args.args[0]["notificationDisabled"])
        body = payment.call_args.args[0]
        self.assertEqual(body["billingType"], "PIX")
        self.assertEqual(body["value"], 199.0)
        self.assertEqual(body["externalReference"], b.reference)
        self.assertEqual(Credit.objects.count(), 0)

    @override_settings(**OPTIONS, BILLING_ALLOW_SANDBOX=False)
    def test_sandbox_cannot_credit_production_settings(self):
        from apps.billing.provider import configured

        self.assertFalse(configured())
        b = self.bill()
        with self.assertRaises(BillingError):
            apply_payment(b.pk, self.paid(b))

    @override_settings(**OPTIONS)
    def test_customer_timeout_recovers_without_second_customer_post(self):
        b = reserve_invoice(
            self.tenant,
            self.plan,
            "PIX",
            Decimal("199"),
            uuid.uuid4(),
            "Pagador",
            "12345678909",
            "x@example.com",
        )
        with patch(
            "apps.billing.services.Asaas.find_customer", return_value={"data": []}
        ), patch(
            "apps.billing.services.Asaas.create_customer",
            side_effect=ProviderUnavailable("timeout"),
        ):
            with self.assertRaises(ProviderUnavailable):
                issue_invoice(b.pk)
        b.refresh_from_db()
        self.assertFalse(b.issuance_attempted)
        found = {
            "id": "cus_123",
            "cpfCnpj": "12345678909",
            "externalReference": f"vdd-customer:sandbox:{self.tenant.pk}",
        }
        with patch(
            "apps.billing.services.Asaas.find_payment", return_value={"data": []}
        ), patch(
            "apps.billing.services.Asaas.find_customer", return_value={"data": [found]}
        ), patch(
            "apps.billing.services.Asaas.create_customer"
        ) as create_customer, patch(
            "apps.billing.services.Asaas.create_payment",
            return_value={"id": "pay_recovered_customer"},
        ) as create_payment:
            reconcile_invoice(b.pk)
        create_customer.assert_not_called()
        self.assertEqual(create_payment.call_count, 1)

    @override_settings(**OPTIONS)
    def test_unrelated_asaas_payment_is_ignored(self):
        from apps.billing.tasks import process_event

        event = BillingEvent.objects.create(
            event_id="sandbox:other",
            kind="PAYMENT_RECEIVED",
            payment_id="pay_elsewhere",
            environment="sandbox",
        )
        with patch(
            "apps.billing.tasks.Asaas.get_payment",
            return_value={"id": "pay_elsewhere", "externalReference": None},
        ):
            process_event(event.pk)
        event.refresh_from_db()
        self.assertIsNotNone(event.processed_at)
        self.assertEqual(Credit.objects.count(), 0)
