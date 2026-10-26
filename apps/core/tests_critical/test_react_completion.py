import uuid
from datetime import date, timedelta
from unittest.mock import patch
from io import StringIO
from django.test import Client, override_settings
from django.db import transaction
from django.conf import settings
from django.core.management import call_command
from rest_framework.response import Response
from django.utils import timezone
from django.contrib.admin.models import LogEntry, ADDITION
from django.contrib.contenttypes.models import ContentType
from .base import CriticalTestCase
from apps.billing.models import Subscription, FreeAccessGrant, Invoice, BillingAudit, Plan
from apps.billing.free_access import grant_free_days, period
from apps.billing.provider import BillingError
from apps.stores.models import Product
from apps.core.models import AdminSelection
from apps.merchant.selection import finalize_selection


class ReactCompletionTests(CriticalTestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="lvh.me")
        self.client.force_login(self.superuser)
        self.sub, _ = Subscription.objects.get_or_create(tenant=self.tenant_a)
        self.url = f"/api/superadmin/tenants/{self.tenant_a.pk}/free-days/"

    def grant(self, days=7, **kw):
        return grant_free_days(
            self.tenant_a,
            days,
            "Cortesia auditada",
            self.superuser,
            kw.pop("token", uuid.uuid4()),
            **kw,
        )

    def test_arbitrary_days_and_calendar_limits(self):
        for days in (1, 2, 7, 15, 30, 45, 60, 90, 180, 365, 730, 10000):
            with self.subTest(days=days):
                self.sub.valid_until = date(2026, 10, 1)
                with patch(
                    "apps.billing.free_access.timezone.localdate",
                    return_value=date(2026, 10, 26),
                ):
                    self.assertEqual(
                        period(self.sub, days),
                        (date(2026, 10, 26), date(2026, 10, 26) + timedelta(days=days)),
                    )
        for days in (0, -1, 1.5, True, "7", 999999999):
            with self.subTest(invalid=days), self.assertRaises(BillingError):
                period(self.sub, days)
        self.sub.valid_until = date.max - timedelta(days=1)
        self.assertEqual(period(self.sub, 1)[1], date.max)
        with self.assertRaises(BillingError):
            period(self.sub, 2)

    def test_business_timezone_date_boundary(self):
        from datetime import datetime, timezone as dt_timezone
        self.sub.valid_until = None
        with timezone.override("America/Sao_Paulo"), patch("django.utils.timezone.now", return_value=datetime(2026,10,26,2,0,tzinfo=dt_timezone.utc)):
            self.assertEqual(period(self.sub,1),(date(2026,10,25),date(2026,10,26)))

    def test_active_extends_and_repeat_does_not_extend_twice(self):
        deadline = timezone.localdate() + timedelta(days=20)
        self.sub.valid_until = deadline
        self.sub.save()
        token = uuid.uuid4()
        with patch("apps.billing.services.Asaas") as remote:
            first = self.grant(730, token=token)
            second = self.grant(730, token=token)
            remote.assert_not_called()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.starts_on, deadline)
        self.assertEqual(first.ends_on, deadline + timedelta(days=730))
        self.assertEqual(FreeAccessGrant.objects.count(), 1)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertTrue(BillingAudit.objects.filter(actor=self.superuser).exists())
        with self.assertRaises(BillingError):
            self.grant(1, token=token)

    def test_expiry_unblocks_but_other_blocks_are_preserved(self):
        for manual, review, billing in (
            (False, False, True),
            (True, False, False),
            (False, True, True),
            (False, False, False),
        ):
            with self.subTest(manual=manual, review=review, billing=billing):
                self.tenant_a.is_active = False
                self.tenant_a.save()
                self.sub.valid_until = timezone.localdate() - timedelta(days=2)
                self.sub.manually_blocked = manual
                self.sub.payment_review = review
                self.sub.billing_suspended = billing
                self.sub.save()
                g = self.grant()
                self.assertEqual(g.starts_on, timezone.localdate())
                self.assertEqual(
                    g.access_after["active"], billing and not manual and not review
                )
                self.assertFalse(g.access_after["billing_suspended"])

    def test_signed_preview_confirmation_replay_and_stale_state(self):
        data = {"days": 7, "reason": "Teste de prévia", "token": str(uuid.uuid4())}
        preview = self.client.post(self.url, data)
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertFalse(FreeAccessGrant.objects.exists())
        data["preview"] = preview.json()["preview"]
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.client.post(self.url, data).json()["grant"], response.json()["grant"]
        )
        data = {"days": 1, "reason": "Segunda concessão", "token": str(uuid.uuid4())}
        data["preview"] = self.client.post(self.url, data).json()["preview"]
        self.sub.refresh_from_db()
        self.sub.manually_blocked = True
        self.sub.save()
        self.assertEqual(self.client.post(self.url, data).status_code, 409)
        self.assertEqual(FreeAccessGrant.objects.count(), 1)
        overview = self.client.get(self.url).json()
        self.assertEqual(overview["total_days"], 7)
        self.assertEqual(len(overview["history"]), 1)

    def test_invalid_form_and_permission_and_csrf(self):
        for days in ("0", "-1", "1.1", "nan", ""):
            self.assertEqual(
                self.client.post(
                    self.url, {"days": days, "reason": "Teste", "token": uuid.uuid4()}
                ).status_code,
                400,
            )
        self.client.force_login(self.admin_a)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        strict = Client(HTTP_HOST="lvh.me", enforce_csrf_checks=True)
        strict.force_login(self.superuser)
        self.assertEqual(
            strict.post(
                self.url, {"days": 7, "reason": "Teste", "token": uuid.uuid4()}
            ).status_code,
            403,
        )
        with self.assertRaises(BillingError):
            grant_free_days(self.tenant_a, 7, "Teste", self.admin_a, uuid.uuid4())

    def merchant(self):
        c = Client(HTTP_HOST=self.host(self.tenant_a))
        c.force_login(self.admin_a)
        return c

    def selection(self, c, query=""):
        r = c.post("/api/merchant/resources/products/selection/" + query)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_all_filtered_more_than_500_confirm_execute_and_replay(self):
        Product.objects.bulk_create(
            [
                Product(
                    tenant=self.tenant_a,
                    category=self.category_a,
                    name=f"Lote {i}",
                    slug=f"lote-{i}",
                    price=1,
                )
                for i in range(510)
            ]
        )
        c = self.merchant()
        selection = self.selection(c, "?q=Lote")
        self.assertEqual(selection["count"], 510)
        data = {"selection": selection["selection"], "action": "mark_as_unavailable"}
        url = "/api/merchant/resources/products/actions/"
        self.assertTrue(c.post(url, data).json()["confirmation_required"])
        self.assertEqual(
            Product.objects.filter(tenant=self.tenant_a, is_available=False).count(), 0
        )
        data["confirmed"] = "yes"
        r = c.post(url, data)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(
            Product.objects.filter(tenant=self.tenant_a, is_available=False).count(),
            510,
        )
        self.product_b.refresh_from_db()
        self.assertTrue(self.product_b.is_available)
        self.assertEqual(c.post(url, data).status_code, 400)

    def test_selection_rejects_filter_drift_and_wrong_actor(self):
        c = self.merchant()
        selection = self.selection(c, "?q=Alpha")
        data = {
            "selection": selection["selection"],
            "action": "mark_as_unavailable",
            "confirmed": "yes",
        }
        self.product_a.name = "Mudou"
        self.product_a.save()
        self.assertEqual(
            c.post("/api/merchant/resources/products/actions/", data).status_code, 400
        )
        other = Client(HTTP_HOST=self.host(self.tenant_b))
        other.force_login(self.admin_b)
        self.assertEqual(
            other.post("/api/merchant/resources/products/actions/", data).status_code,
            403,
        )
        self.assertIsNone(
            AdminSelection.objects.get(pk=selection["selection"]).consumed_at
        )

    def test_recent_activity_scoped_and_deleted_record(self):
        ct = ContentType.objects.get_for_model(Product)
        for obj, user in (
            (self.product_a, self.admin_a),
            (self.product_b, self.admin_b),
        ):
            LogEntry.objects.log_actions(
                user_id=user.pk,
                queryset=Product.objects.filter(pk=obj.pk),
                action_flag=ADDITION,
            )
        c = self.merchant()
        r = c.get("/api/merchant/activity/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["count"], 1)
        self.assertEqual(r.json()["rows"][0]["object"], str(self.product_a))
        self.assertNotIn("Beta", str(r.json()))
        r = c.post(
            "/api/merchant/resources/products/actions/",
            {
                "ids": [self.product_a.pk],
                "action": "delete_selected",
                "confirmed": "yes",
            },
        )
        self.assertEqual(r.status_code, 200, r.content)
        r = c.get("/api/merchant/activity/")
        self.assertTrue(any(row["url"] is None for row in r.json()["rows"]))
        global_r = self.client.get("/api/superadmin/activity/")
        self.assertEqual(global_r.status_code, 200, global_r.content)

    def test_existing_invoice_unchanged_and_expiry_is_exclusive(self):
        from django.test import override_settings
        from apps.billing.services import suspend_due

        invoice = Invoice.objects.create(
            tenant=self.tenant_a,
            status="PAID",
            plan_name="Original",
            amount=10,
            due_date=timezone.localdate(),
            method="PIX",
            environment="sandbox",
        )
        before = Invoice.objects.filter(pk=invoice.pk).values().get()
        self.sub.grace_days = 0
        self.sub.save()
        grant = self.grant(1)
        self.assertEqual(Invoice.objects.filter(pk=invoice.pk).values().get(), before)
        with override_settings(BILLING_ENABLED=True):
            suspend_due(today=grant.ends_on - timedelta(days=1))
            self.tenant_a.refresh_from_db()
            self.assertTrue(self.tenant_a.is_active)
            suspend_due(today=grant.ends_on)
            self.tenant_a.refresh_from_db()
            self.assertFalse(self.tenant_a.is_active)

    def test_free_days_then_paid_months_keep_entire_grant(self):
        from apps.billing.services import extend_locked, add_months

        # A concessão altera o aniversário efetivo; meses pagos devem partir
        # do novo vencimento sem absorver nenhum dos dias concedidos.
        fixed_today = date(2026, 11, 1)
        with patch("apps.billing.free_access.timezone.localdate", return_value=fixed_today), patch(
            "apps.billing.services.timezone.localdate", return_value=fixed_today
        ):
            for months in (1, 3, 12):
                with self.subTest(months=months):
                    self.sub.valid_until = date(2026, 12, 1)
                    self.sub.anchor_day = 1
                    self.sub.save(update_fields=["valid_until", "anchor_day"])
                    grant = self.grant(7)
                    self.sub.refresh_from_db()
                    self.assertEqual(grant.ends_on, date(2026, 12, 8))
                    self.assertEqual(self.sub.anchor_day, 8)
                    credit = extend_locked(self.sub, months, reason="Pagamento simulado")
                    expected = add_months(date(2026, 12, 8), months, 8)
                    self.assertEqual(credit.valid_until, expected)
                    self.assertEqual(self.sub.valid_until, expected)

    def test_old_free_grant_before_fix_preserves_days_on_paid_renewal(self):
        from apps.billing.services import extend_locked

        with patch("apps.billing.free_access.timezone.localdate", return_value=date(2026, 11, 1)), patch(
            "apps.billing.services.timezone.localdate", return_value=date(2026, 11, 1)
        ):
            self.sub.valid_until = date(2026, 12, 1)
            self.sub.anchor_day = 1
            self.sub.save(update_fields=["valid_until", "anchor_day"])
            self.grant(7)
            # Simula o registro persistido por uma versão antiga: cortesia
            # registrada, validade estendida, porém aniversário ainda antigo.
            self.sub.refresh_from_db()
            self.sub.anchor_day = 1
            self.sub.save(update_fields=["anchor_day"])
            paid = extend_locked(self.sub, 1)
            self.assertEqual(self.sub.anchor_day, 8)
            self.assertEqual(paid.valid_until, date(2027, 1, 8))

    def test_paid_months_free_days_paid_months_and_short_months(self):
        from apps.billing.services import extend_locked

        # O aniversário original mantém o dia 31 mesmo ao passar por fevereiro.
        self.sub.valid_until = date(2027, 1, 31)
        self.sub.anchor_day = 31
        self.sub.save(update_fields=["valid_until", "anchor_day"])
        with patch("apps.billing.free_access.timezone.localdate", return_value=date(2027, 1, 1)), patch(
            "apps.billing.services.timezone.localdate", return_value=date(2027, 1, 1)
        ):
            paid = extend_locked(self.sub, 1)
            self.assertEqual(paid.valid_until, date(2027, 2, 28))
            self.assertEqual(self.sub.anchor_day, 31)
            paid = extend_locked(self.sub, 1)
            self.assertEqual(paid.valid_until, date(2027, 3, 31))
            self.assertEqual(self.sub.anchor_day, 31)
            gift = self.grant(7)
            self.assertEqual(gift.ends_on, date(2027, 4, 7))
            self.sub.refresh_from_db()
            self.assertEqual(self.sub.anchor_day, 7)
            self.assertEqual(extend_locked(self.sub, 1).valid_until, date(2027, 5, 7))

        self.sub.valid_until = date(2028, 1, 31)
        self.sub.anchor_day = 31
        self.sub.save(update_fields=["valid_until", "anchor_day"])
        with patch("apps.billing.free_access.timezone.localdate", return_value=date(2028, 1, 1)), patch(
            "apps.billing.services.timezone.localdate", return_value=date(2028, 1, 1)
        ):
            gift = self.grant(29)
            self.assertEqual(gift.ends_on, date(2028, 2, 29))
            self.sub.refresh_from_db()
            self.assertEqual(self.sub.anchor_day, 29)
            self.assertEqual(extend_locked(self.sub, 1).valid_until, date(2028, 3, 29))

    def test_rejected_merchant_bulk_delete_keeps_selection_available(self):
        from apps.merchant.registry import resource_admin

        merchant = self.merchant()
        token = self.selection(merchant, "?q=Alpha")["selection"]
        url = "/api/merchant/resources/products/actions/"
        payload = {"selection": token, "action": "delete_selected", "confirmed": "yes"}
        admin = resource_admin("products")
        with patch.object(admin, "get_deleted_objects", return_value=([], {}, [], ["Protegido"])):
            denied = merchant.post(url, payload)
        self.assertEqual(denied.status_code, 400, denied.content)
        self.assertIsNone(AdminSelection.objects.get(pk=token).consumed_at)
        approved = merchant.post(url, payload)
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertIsNotNone(AdminSelection.objects.get(pk=token).consumed_at)

    def test_rejected_superadmin_bulk_delete_keeps_selection_available(self):
        from apps.superpanel.registry import resource_admin

        plan = Plan.objects.create(name="Plano para teste", months=35, monthly_price=149)
        endpoint = "/api/superadmin/resources/billing-plan/selection/?q=Plano"
        result = self.client.post(endpoint)
        self.assertEqual(result.status_code, 200, result.content)
        token = result.json()["selection"]
        action = "/api/superadmin/resources/billing-plan/actions/"
        data = {"selection": token, "action": "delete_selected", "confirmed": "yes"}
        admin = resource_admin("billing-plan")
        with patch.object(admin, "get_deleted_objects", return_value=([], {}, [], ["Protegido"])):
            denied = self.client.post(action, data)
        self.assertEqual(denied.status_code, 400, denied.content)
        self.assertTrue(Plan.objects.filter(pk=plan.pk).exists())
        self.assertIsNone(AdminSelection.objects.get(pk=token).consumed_at)
        approved = self.client.post(action, data)
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertIsNotNone(AdminSelection.objects.get(pk=token).consumed_at)

    def test_action_error_response_rolls_back_mutations(self):
        merchant = self.merchant()
        token = self.selection(merchant, "?q=Alpha")["selection"]
        snapshot = AdminSelection.objects.get(pk=token)
        with transaction.atomic():
            Product.objects.filter(pk=self.product_a.pk).update(is_available=False)
            finalize_selection(snapshot, Response({"detail": "Recusado"}, status=400))
        self.product_a.refresh_from_db()
        self.assertTrue(self.product_a.is_available)
        snapshot.refresh_from_db()
        self.assertIsNone(snapshot.consumed_at)

    def test_expired_admin_selection_cleanup_and_schedule(self):
        merchant = self.merchant()
        expired = self.selection(merchant, "?q=Alpha")["selection"]
        valid = self.selection(merchant, "?q=Alpha")["selection"]
        AdminSelection.objects.filter(pk=expired).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        output = StringIO()
        call_command("prune_admin_selections", stdout=output)
        self.assertFalse(AdminSelection.objects.filter(pk=expired).exists())
        self.assertTrue(AdminSelection.objects.filter(pk=valid).exists())
        self.assertEqual(
            settings.CELERY_BEAT_SCHEDULE["admin-selection-cleanup"]["task"],
            "apps.core.tasks.prune_expired_admin_selections",
        )

    def test_new_store_form_includes_optional_days_and_reason(self):
        doc = self.client.get("/api/superadmin/resources/tenants-tenant/new/").json()
        names = {f["name"]: f for f in doc["fields"]}
        self.assertIn("free_days", names)
        self.assertEqual(names["free_days"]["min"], 1)
        self.assertIn("free_days_reason", names)

    @override_settings(BILLING_ENABLED=True)
    def test_create_store_with_days_preserves_onboarding(self):
        from apps.merchant.tests import MerchantAPITests
        from apps.tenants.models import Tenant

        url = "/api/superadmin/resources/tenants-tenant/new/"
        doc = self.client.get(url).json()
        data = MerchantAPITests.payload(self, doc)
        data.update(
            name="Loja nova dias",
            slug="nova-dias",
            whatsapp_number="5511999995555",
            merchant_name="Pessoa Teste",
            merchant_email="nova@example.com",
            free_days="45",
            free_days_reason="Cadastro de homologação",
        )
        data.pop("grant_free_month", None)
        preview = self.client.post(url, data)
        self.assertEqual(preview.status_code, 200, preview.content[-5000:])
        self.assertFalse(Tenant.objects.filter(slug="nova-dias").exists())
        data["free_days_preview"] = preview.json()["free_days_preview"]
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200, response.content[-5000:])
        tenant = Tenant.objects.get(pk=response.json()["id"])
        grant = FreeAccessGrant.objects.get(subscription__tenant=tenant)
        self.assertEqual(grant.days, 45)
        tenant.refresh_from_db()
        self.assertTrue(tenant.is_active)
        self.assertTrue(tenant.users.filter(is_tenant_admin=True).exists())
        self.assertFalse(Invoice.objects.filter(tenant=tenant).exists())


from django.test import TransactionTestCase
from django.db import connection, close_old_connections
from django.contrib.auth import get_user_model
from apps.tenants.models import Tenant
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier


@skipUnless(connection.vendor == "postgresql", "Requer locks reais do PostgreSQL")
class FreeDaysConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Concorrência", slug="concorrencia", whatsapp_number="5511999993333"
        )
        self.actor = get_user_model().objects.create_superuser(
            username="concurrent-root",
            email="test@example.com",
            password="TestOnly123!",
        )
        Subscription.objects.create(tenant=self.tenant)

    def concurrent(self, tokens):
        barrier = Barrier(2)

        def run(token):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.actor.pk)
                tenant = Tenant.objects.get(pk=self.tenant.pk)
                barrier.wait(timeout=10)
                return grant_free_days(tenant, 7, "Concorrência", actor, token).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, tokens))

    def test_same_token_applies_once(self):
        token = uuid.uuid4()
        ids = self.concurrent([token, token])
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(FreeAccessGrant.objects.count(), 1)
        self.assertEqual(
            Subscription.objects.get(tenant=self.tenant).valid_until,
            timezone.localdate() + timedelta(days=7),
        )

    def test_distinct_tokens_serialize_without_lost_days(self):
        self.concurrent([uuid.uuid4(), uuid.uuid4()])
        self.assertEqual(FreeAccessGrant.objects.count(), 2)
        self.assertEqual(
            Subscription.objects.get(tenant=self.tenant).valid_until,
            timezone.localdate() + timedelta(days=14),
        )
