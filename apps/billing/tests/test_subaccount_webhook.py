import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.billing.models import BillingEvent, TenantPaymentAccount
from apps.billing.online import online_payment_available, request_subaccount, sync_pending_subaccounts
from apps.billing.tasks import process_event
from apps.tenants.models import Tenant


@override_settings(
    BILLING_ENABLED=True,
    ASAAS_ENVIRONMENT="sandbox",
    ASAAS_API_KEY="platform-key",
    ASAAS_WEBHOOK_TOKEN="w" * 40,
)
class SubaccountWebhookTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja aguardando Asaas",
            slug="loja-aguardando-asaas",
            whatsapp_number="5511999991111",
            sale_mode="online",
        )
        self.account = TenantPaymentAccount.objects.create(
            tenant=self.tenant,
            enabled=True,
            terms_accepted=True,
            status=TenantPaymentAccount.Status.PENDING,
            provider_account_id="acc_status_123",
            legal_name="Loja aguardando Asaas",
            document="12345678000190",
            email="loja@example.com",
            mobile_phone="5511999991111",
            income_value=Decimal("5000"),
            address="Rua A",
            address_number="1",
            province="Centro",
            postal_code="01001000",
        )
        self.account.set_api_key("subaccount-key")
        self.account.save(update_fields=["encrypted_api_key"])

    def post_status(self, event):
        return self.client.post(
            "/integracoes/asaas/webhook/",
            data=json.dumps(
                {
                    "id": "evt-" + event.lower(),
                    "event": event,
                    "account": {"id": self.account.provider_account_id},
                    "accountStatus": {"general": "APPROVED"},
                }
            ),
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="w" * 40,
        )

    @patch("apps.billing.tasks.process_event.delay")
    def test_general_approval_event_is_queued_and_enables_online_payment(self, enqueue):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_status("ACCOUNT_STATUS_GENERAL_APPROVAL_APPROVED")
        self.assertEqual(response.status_code, 200)
        event = BillingEvent.objects.get()
        enqueue.assert_called_once_with(event.pk)

        process_event(event.pk)
        self.account.refresh_from_db()
        self.assertEqual(self.account.status, TenantPaymentAccount.Status.APPROVED)
        self.assertIsNotNone(self.account.approved_at)
        self.assertTrue(self.account.is_ready)
        self.assertTrue(online_payment_available(self.tenant))
        self.assertIsNotNone(BillingEvent.objects.get(pk=event.pk).processed_at)

    @patch("apps.billing.tasks.process_event.delay")
    def test_rejected_event_blocks_online_payment_and_duplicate_is_idempotent(self, enqueue):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_status("ACCOUNT_STATUS_DOCUMENT_REJECTED")
        self.assertEqual(response.status_code, 200)
        event = BillingEvent.objects.get()
        process_event(event.pk)
        process_event(event.pk)

        self.account.refresh_from_db()
        self.assertEqual(self.account.status, TenantPaymentAccount.Status.REJECTED)
        self.assertFalse(self.account.is_ready)
        self.assertEqual(BillingEvent.objects.get(pk=event.pk).attempts, 1)

    @patch(
        "apps.billing.online.Asaas.request",
        return_value={"general": "APPROVED", "documentation": "APPROVED"},
    )
    def test_periodic_sync_recovers_when_webhook_is_unavailable(self, request):
        sync_pending_subaccounts()
        self.account.refresh_from_db()
        self.assertEqual(self.account.status, TenantPaymentAccount.Status.APPROVED)
        request.assert_called_once_with("GET", "/myAccount/status/")

    @override_settings(ASAAS_WEBHOOK_URL="https://app.example.com/integracoes/asaas/webhook/")
    @patch("apps.billing.online.Asaas.request", return_value={"id": "wh_123"})
    @patch(
        "apps.billing.online.Asaas.create_subaccount",
        return_value={"id": "acc_new", "walletId": "wal_new", "apiKey": "sub-key"},
    )
    def test_new_subaccount_provisions_account_status_webhook(self, create, request):
        self.account.provider_account_id = ""
        self.account.encrypted_api_key = ""
        self.account.save(update_fields=["provider_account_id", "encrypted_api_key"])

        request_subaccount(self.account)

        payload = request.call_args.kwargs["json"]
        self.assertEqual(payload["url"], "https://app.example.com/integracoes/asaas/webhook/")
        self.assertEqual(payload["authToken"], "w" * 40)
        self.assertIn("ACCOUNT_STATUS_GENERAL_APPROVAL_APPROVED", payload["events"])
