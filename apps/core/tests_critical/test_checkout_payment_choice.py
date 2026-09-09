import json
from decimal import Decimal

from apps.billing.models import TenantPaymentAccount
from apps.orders.models import Order

from .base import CriticalTestCase


class CheckoutPaymentChoiceCriticalTests(CriticalTestCase):
    def setUp(self):
        self.tenant_a.online_payments_allowed = True
        self.tenant_a.save(update_fields=["online_payments_allowed"])
        self.account = TenantPaymentAccount.objects.create(
            tenant=self.tenant_a,
            enabled=True,
            terms_accepted=True,
            status=TenantPaymentAccount.Status.APPROVED,
            provider_account_id="acc_checkout_choice",
            encrypted_api_key="encrypted-test-key",
            legal_name="Loja Alpha",
            document="12345678000190",
            email="alpha@example.com",
            mobile_phone="11999999999",
            income_value=Decimal("5000.00"),
            address="Rua Alpha",
            address_number="10",
            province="Centro",
            postal_code="01001000",
        )
        self.tenant_a.refresh_from_db()
        self.host_a = self.host(self.tenant_a)

    def _open_checkout(self):
        response = self.client.post(
            "/checkout/add/",
            json.dumps({"product_id": self.product_a.pk, "quantity": 1}),
            content_type="application/json",
            HTTP_HOST=self.host_a,
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/checkout/checkout/", HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 200)
        return response, self.client.session["checkout_token"]

    def _submit(self, token, *, payment_flow, payment_method):
        return self.client.post(
            "/checkout/checkout/",
            {
                "checkout_token": token,
                "full_name": "Cliente",
                "phone": "11999999999",
                "delivery_type": "pickup",
                "payment_flow": payment_flow,
                "payment_method": payment_method,
            },
            HTTP_HOST=self.host_a,
        )

    def test_online_ready_checkout_offers_online_or_direct_payment(self):
        response, _token = self._open_checkout()
        body = response.content.decode("utf-8")

        self.assertIn("Pagar online", body)
        self.assertIn("Pagar na entrega ou retirada", body)
        self.assertIn("Pagamento online seguro", body)
        self.assertNotIn("As taxas de cada operação são cobradas pelo Asaas", body)
        self.assertNotIn("Configurações de Conta &gt; Taxas", body)

    def test_customer_can_choose_pix_directly_with_store(self):
        _response, token = self._open_checkout()
        response = self._submit(
            token,
            payment_flow="in_person",
            payment_method="pix",
        )
        self.assertEqual(response.status_code, 200)

        order = Order.objects.get(tenant=self.tenant_a)
        self.assertEqual(order.payment_flow, "in_person")
        self.assertEqual(order.payment_method, "pix")
        body = response.content.decode("utf-8")
        self.assertIn("Abrir WhatsApp e enviar", body)
        self.assertNotIn("Pagar online com Asaas", body)

    def test_customer_can_choose_online_pix(self):
        _response, token = self._open_checkout()
        response = self._submit(
            token,
            payment_flow="online",
            payment_method="pix",
        )
        self.assertEqual(response.status_code, 200)

        order = Order.objects.get(tenant=self.tenant_a)
        self.assertEqual(order.payment_flow, "online")
        self.assertEqual(order.payment_method, "pix")
        self.assertIn("Pagar online com Asaas", response.content.decode("utf-8"))

    def test_online_flow_rejects_debit_card(self):
        _response, token = self._open_checkout()
        response = self._submit(
            token,
            payment_flow="online",
            payment_method="debit_card",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.filter(tenant=self.tenant_a).exists())
