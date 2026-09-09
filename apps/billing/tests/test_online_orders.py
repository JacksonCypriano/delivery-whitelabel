from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, RequestFactory, override_settings

from apps.billing.models import OrderPayment, TenantPaymentAccount
from apps.billing.online import apply_checkout_event, create_order_checkout
from apps.billing.provider import BillingError
from apps.orders.models import Order
from apps.orders.services import build_whatsapp_message
from apps.tenants.models import Tenant


@override_settings(BILLING_ENABLED=True, ASAAS_ENVIRONMENT="sandbox", ASAAS_API_KEY="platform-key", ASAAS_WEBHOOK_TOKEN="x" * 40)
class OnlineOrderPaymentTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Loja online", slug="loja-online", whatsapp_number="5511999992222", sale_mode="online", online_payments_allowed=True)
        self.account = TenantPaymentAccount.objects.create(
            tenant=self.tenant, enabled=True, terms_accepted=True, status=TenantPaymentAccount.Status.APPROVED,
            provider_account_id="acc_123", legal_name="Loja online", document="12345678000190",
            email="loja@example.com", mobile_phone="5511999992222", income_value=Decimal("5000"),
            address="Rua A", address_number="1", province="Centro", postal_code="01001000",
        )
        self.account.set_api_key("subaccount-key")
        self.account.save(update_fields=["encrypted_api_key"])
        self.order = Order.objects.create(
            tenant=self.tenant, customer_name="Cliente", customer_phone="5511988887777",
            subtotal=Decimal("50.00"), total=Decimal("50.00"), delivery_fee=Decimal("0"),
            delivery_type="pickup", payment_flow="online", payment_method="pix",
        )
        self.factory = RequestFactory()

    @patch(
        "apps.billing.online.Asaas.create_checkout",
        return_value={
            "id": "chk_123",
            "link": "https://sandbox.asaas.com/checkoutSession/show/chk_123",
        },
    )
    def test_checkout_is_created_in_tenant_subaccount(self, create_checkout):
        request = self.factory.get("/pedido/")
        payment = create_order_checkout(self.order, request)
        self.assertEqual(payment.provider_account_id, "acc_123")
        self.assertEqual(
            payment.checkout_url,
            "https://sandbox.asaas.com/checkoutSession/show/chk_123",
        )
        self.assertEqual(payment.status, OrderPayment.Status.PENDING)
        create_checkout.assert_called_once()

    @patch("apps.billing.online.Asaas.create_checkout", return_value={"id": "chk_fallback"})
    def test_checkout_uses_documented_fallback_when_link_is_missing(self, create_checkout):
        request = self.factory.get("/pedido/")
        payment = create_order_checkout(self.order, request)
        self.assertEqual(
            payment.checkout_url,
            "https://sandbox.asaas.com/checkoutSession/show/chk_fallback",
        )

    def test_payment_status_template_surfaces_provider_errors(self):
        from django.template.loader import get_template

        source = get_template("checkout/payment_status.html").template.source
        self.assertIn("checkout/partials/_integrity_notices.html", source)

    def test_in_person_pix_never_creates_asaas_checkout(self):
        self.order.payment_flow = "in_person"
        self.order.save(update_fields=["payment_flow"])

        with self.assertRaisesMessage(BillingError, "Este pedido não utiliza pagamento online"):
            create_order_checkout(self.order, self.factory.get("/pedido/"))

    @patch(
        "apps.billing.online.Asaas.get_checkout",
        return_value={"id": "chk_123", "externalReference": "placeholder", "status": "PAID"},
    )
    def test_existing_checkout_can_be_reconciled_after_online_permission_is_revoked(self, get_checkout):
        payment = OrderPayment.objects.create(
            order=self.order, tenant=self.tenant, provider_account_id="acc_123",
            checkout_id="chk_123", checkout_url="https://sandbox.asaas.com/checkoutSession/show?id=chk_123",
            external_reference="vdd-order:sandbox:%s:%s" % (self.order.pk, self.order.public_token),
            confirmation_code="VDD-1-REVOKE01", method="pix", amount=self.order.total,
        )
        get_checkout.return_value["externalReference"] = payment.external_reference

        self.tenant.online_payments_allowed = False
        self.tenant.save(update_fields=["online_payments_allowed"])
        self.account.refresh_from_db()
        self.account.save(update_fields=["updated_at"])
        self.assertFalse(self.account.is_ready)

        from apps.billing.online import refresh_order_payment

        refresh_order_payment(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, OrderPayment.Status.PAID)
        get_checkout.assert_called_once_with("chk_123")

    def test_paid_event_generates_public_confirmation_code(self):
        payment = OrderPayment.objects.create(
            order=self.order, tenant=self.tenant, provider_account_id="acc_123",
            checkout_id="chk_123", checkout_url="https://sandbox.asaas.com/checkoutSession/show?id=chk_123",
            external_reference="vdd-order:sandbox:%s:%s" % (self.order.pk, self.order.public_token),
            confirmation_code="VDD-1-ABC12345", method="pix", amount=self.order.total,
        )
        apply_checkout_event("chk_123", {"id": "chk_123", "externalReference": payment.external_reference, "status": "PAID"}, "CHECKOUT_PAID")
        payment.refresh_from_db()
        self.assertEqual(payment.status, OrderPayment.Status.PAID)
        self.assertIn("VDD-1-ABC12345", build_whatsapp_message(self.order))
