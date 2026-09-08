from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.fees import parse_asaas_fees, sync_platform_fee_snapshot
from apps.billing.models import AsaasFeeSnapshot, BillingSettings, Plan
from apps.billing.services import price_for
from apps.billing.tasks import monitor_asaas_fees


OPTIONS = dict(
    BILLING_ENABLED=True,
    ASAAS_ENVIRONMENT="sandbox",
    ASAAS_API_KEY="test-key",
    ASAAS_WEBHOOK_TOKEN="x" * 40,
    SUPERADMIN_PUBLIC_URL="https://admin.example.com",
)


def fee_payload(*, pix="1.99", card="2.99", discounted=False):
    return {
        "payment": {
            "bankSlip": {
                "defaultValue": 1.99,
                "discountValue": 0.99 if discounted else None,
                "expirationDate": "2026-12-02 00:00:00" if discounted else None,
                "daysToReceive": 1,
            },
            "creditCard": {
                "operationValue": 0.49,
                "oneInstallmentPercentage": float(card),
                "upToSixInstallmentsPercentage": 3.49,
                "upToTwelveInstallmentsPercentage": 3.99,
                "upToTwentyOneInstallmentsPercentage": 4.29,
                "discountOneInstallmentPercentage": 1.99 if discounted else None,
                "discountUpToSixInstallmentsPercentage": 2.49 if discounted else None,
                "discountUpToTwelveInstallmentsPercentage": 2.99 if discounted else None,
                "discountUpToTwentyOneInstallmentsPercentage": 3.29 if discounted else None,
                "hasValidDiscount": discounted,
                "daysToReceive": 32,
                "discountExpiration": "2026-12-02 00:00:00" if discounted else None,
            },
            "pix": {
                "fixedFeeValue": float(pix),
                "fixedFeeValueWithDiscount": 0.99 if discounted else None,
                "discountExpiration": "2026-12-02 00:00:00" if discounted else None,
                "monthlyCreditsWithoutFee": 100,
            },
        },
        "invoice": {"feeValue": 0.49},
        "childAccount": {"creationFeeValue": 12.90},
    }


@override_settings(**OPTIONS)
class AsaasFeeTests(TestCase):
    def test_parser_uses_promotion_only_until_expiration(self):
        before = timezone.make_aware(datetime(2026, 9, 8, 12, 0))
        after = timezone.make_aware(datetime(2026, 12, 3, 12, 0))
        payload = fee_payload(discounted=True)

        promo = parse_asaas_fees(payload, now=before)
        regular = parse_asaas_fees(payload, now=after)

        self.assertEqual(promo["pix"]["effective"], Decimal("0.99"))
        self.assertEqual(promo["card"]["effective"]["1"], Decimal("1.99"))
        self.assertEqual(regular["pix"]["effective"], Decimal("1.99"))
        self.assertEqual(regular["card"]["effective"]["1"], Decimal("2.99"))
        self.assertEqual(promo["invoice_fee"], Decimal("0.49"))
        self.assertEqual(promo["child_account_fee"], Decimal("12.9"))

    @patch("apps.billing.fees.Asaas.request")
    def test_snapshot_is_created_only_when_relevant_fee_changes(self, request):
        request.return_value = fee_payload()
        first, created, _ = sync_platform_fee_snapshot()
        self.assertTrue(created)
        second, created, _ = sync_platform_fee_snapshot()
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AsaasFeeSnapshot.objects.count(), 1)

        request.return_value = fee_payload(pix="2.49")
        _third, created, _ = sync_platform_fee_snapshot()
        self.assertTrue(created)
        self.assertEqual(AsaasFeeSnapshot.objects.count(), 2)

    def test_card_price_uses_asaas_snapshot_and_preserves_pix_net(self):
        AsaasFeeSnapshot.objects.create(
            environment="sandbox",
            fingerprint="x" * 64,
            payload=fee_payload(discounted=True),
            pix_fee=Decimal("0.99"),
            card_fixed_fee=Decimal("0.49"),
            card_1x_percent=Decimal("1.99"),
        )
        policy = BillingSettings.current()
        policy.card_enabled = True
        policy.save(update_fields=["card_enabled"])
        plan = Plan.objects.get(months=1)

        # R$ 202,54 no cartão deixa aproximadamente o mesmo líquido que
        # R$ 199,00 no Pix considerando apenas a tarifa do meio de pagamento.
        self.assertEqual(price_for(plan, "CREDIT_CARD"), Decimal("202.54"))

    @patch("apps.billing.tasks._send_fee_whatsapp", return_value=1)
    @patch("apps.billing.fees.Asaas.request")
    def test_monitor_alerts_once_when_fee_changes(self, request, send):
        request.return_value = fee_payload()
        self.assertEqual(monitor_asaas_fees(), 0)
        send.assert_not_called()

        request.return_value = fee_payload(pix="2.49")
        self.assertEqual(monitor_asaas_fees(), 1)
        self.assertEqual(send.call_count, 1)

        self.assertEqual(monitor_asaas_fees(), 0)
        self.assertEqual(send.call_count, 1)
