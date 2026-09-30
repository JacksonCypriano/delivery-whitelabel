from decimal import Decimal
from unittest.mock import patch, Mock

from django.test import TestCase, override_settings
from apps.integrations.models import (
    WhatsAppCheckout,
    WhatsAppCheckoutReceipt,
    WhatsAppOrderNotice,
    TenantWhatsAppConversation,
)
from apps.integrations.whatsapp_agent.checkout import handle_checkout
from apps.integrations.whatsapp_agent.checkout_payments import (
    issue_pix,
    apply_pix_event,
    reference,
)
from apps.integrations.whatsapp_agent.provider import extract_text
from apps.integrations.whatsapp_agent.client import TenantEvolutionClient
from apps.orders.models import Order
from apps.orders import cart_service, inventory
from apps.stores.models import (
    Category,
    Product,
    CustomizationGroup,
    CustomizationGroupLabel,
    CustomizationOption,
)
from apps.tenants.models import Tenant, DeliveryZone
from apps.billing.models import BillingEvent
from apps.billing.provider import BillingError


@override_settings(WHATSAPP_AGENT_OLLAMA_ENABLED=False)
class WhatsAppCheckoutTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Bella Massa",
            slug="bella",
            whatsapp_number="5511999999991",
            pickup_address="Rua A",
            pickup_number="10",
            pickup_city="Itapevi",
            pickup_neighborhood="Centro",
        )
        self.category = Category.objects.create(tenant=self.tenant, name="Lanches")
        self.product = Product.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="X Burger",
            price=Decimal("20"),
            stock=Decimal("10"),
        )
        self.phone = "5511999999992"
        self.counter = 0

    def say(self, text):
        self.counter += 1
        return handle_checkout(self.tenant, self.phone, f"m{self.counter}", text)

    def click(self, response, action):
        key = next(k for k, label in response.choices if k.split(":", 2)[2] == action)
        return self.say(key)

    def current(self):
        return WhatsAppCheckout.objects.latest("pk")

    def add(self, notes="sem observacao", quantity="2"):
        r = self.say("novo pedido")
        r = self.click(r, f"product:{self.product.pk}")
        self.say(quantity)
        return self.say(notes)

    def prepare(self, method="cash"):
        self.add("retirar cebola")
        self.say("finalizar")
        self.say("Jackson")
        self.say("retirada")
        r = self.say("dinheiro" if method == "cash" else method)
        if method == "cash":
            r = self.say("100,00")
        if method == "pix online":
            r = self.say("24971563792")
        return r

    def online(self):
        # Production account availability has dedicated billing regression tests.
        patches = [
            patch(
                "apps.integrations.whatsapp_agent.checkout.online_payment_available",
                return_value=True,
            ),
            patch(
                "apps.integrations.whatsapp_agent.checkout_payments.online_payment_available",
                return_value=True,
            ),
            patch.object(
                Tenant, "payment_account", Mock(provider_account_id="acc_test")
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        r = self.prepare("pix online")
        self.click(r, "confirm")
        return self.current()

    def remote(self, c, status="RECEIVED", **changes):
        return {
            "id": c.provider_id,
            "externalReference": reference(c),
            "billingType": "PIX",
            "value": "40.00",
            "status": status,
            **changes,
        }

    def bind(self, c):
        c.provider_id = "pay_test"
        c.status = "pending"
        c.save()
        return c

    def event(self, c):
        return BillingEvent.objects.create(
            event_id=f"e{BillingEvent.objects.count()}",
            payment_id=c.provider_id,
            environment="sandbox",
            kind="PAYMENT_RECEIVED",
        )

    def test_cash_checkout_notes_change_and_totals(self):
        r = self.prepare()
        self.assertIn("retirar cebola", r.text)
        self.assertIn("60,00", r.text)
        self.assertEqual(Order.objects.count(), 0)
        self.click(r, "confirm")
        order = Order.objects.get()
        self.assertEqual(order.total, Decimal("40"))
        self.assertEqual(order.payment_change_for, "100.00")
        self.assertEqual(order.items.get().notes, "retirar cebola")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal("8"))
        self.assertEqual(WhatsAppOrderNotice.objects.count(), 2)
        self.assertEqual(
            set(WhatsAppOrderNotice.objects.values_list("recipient", flat=True)),
            {self.phone, self.tenant.whatsapp_number},
        )

    def test_order_confirmation_uses_separate_operations_whatsapp(self):
        self.tenant.whatsapp_order_number = "5511988887777"
        self.tenant.save(update_fields=["whatsapp_order_number"])

        r = self.prepare()
        self.click(r, "confirm")

        self.assertEqual(
            set(WhatsAppOrderNotice.objects.values_list("recipient", flat=True)),
            {self.phone, "5511988887777"},
        )

    def test_order_confirmation_deduplicates_same_customer_and_operations_number(self):
        self.tenant.whatsapp_order_number = self.phone
        self.tenant.save(update_fields=["whatsapp_order_number"])

        r = self.prepare()
        self.click(r, "confirm")

        self.assertEqual(WhatsAppOrderNotice.objects.count(), 1)

    def test_duplicate_message_does_not_add_twice(self):
        self.add()
        c = self.current()
        receipt = WhatsAppCheckoutReceipt.objects.latest("pk")
        handle_checkout(self.tenant, self.phone, receipt.message_id, "sem observacao")
        self.assertEqual(c.cart.items.get().quantity, 2)

    def test_duplicate_confirmation_creates_one_order(self):
        r = self.prepare()
        self.click(r, "confirm")
        receipt = WhatsAppCheckoutReceipt.objects.latest("pk")
        handle_checkout(self.tenant, self.phone, receipt.message_id, "confirmar")
        self.assertEqual(Order.objects.count(), 1)

    def test_stale_button_cannot_confirm(self):
        r = self.prepare()
        old = r.choices[0][0]
        self.say("carrinho")
        result = self.say(old)
        self.assertIn("etapa anterior", result.text)
        self.assertFalse(Order.objects.exists())

    def test_price_changes_require_reconfirmation(self):
        r = self.prepare("pix")
        Product.objects.filter(pk=self.product.pk).update(price=Decimal("30"))
        changed = self.click(r, "confirm")
        self.assertIn("60,00", changed.text)
        self.assertFalse(Order.objects.exists())
        self.click(changed, "confirm")
        self.assertEqual(Order.objects.get().total, Decimal("60"))

    def test_stock_insufficient_keeps_cart(self):
        r = self.prepare("pix")
        Product.objects.filter(pk=self.product.pk).update(stock=Decimal("1"))
        response = self.click(r, "confirm")
        self.assertIn("Estoque insuficiente", response.text)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.current().cart.items.count(), 1)

    def test_remove_item(self):
        self.add()
        self.say("remover 1")
        self.assertEqual(self.current().cart.items.count(), 0)

    def test_cart_survives_context_expiry(self):
        self.add()
        TenantWhatsAppConversation.objects.update(context={})
        self.assertIn("X Burger", self.say("carrinho").text)

    def test_tenant_and_phone_isolation(self):
        self.add()
        self.phone = "5511999999993"
        self.assertIn("vazio", self.say("carrinho").text)
        self.assertEqual(WhatsAppCheckout.objects.count(), 2)

    def test_additions_required_and_notes(self):
        label = CustomizationGroupLabel.objects.create(
            tenant=self.tenant, name="Queijos"
        )
        g = CustomizationGroup.objects.create(
            tenant=self.tenant,
            category=self.category,
            label=label,
            min_options=1,
            max_options=1,
        )
        o = CustomizationOption.objects.create(
            tenant=self.tenant, group=g, name="Cheddar", price=Decimal("4")
        )
        r = self.say("novo pedido")
        r = self.click(r, f"product:{self.product.pk}")
        r = self.say("2")
        r = self.click(r, "done")
        self.assertIn("Escolha de 1 a 1", r.text)
        r = self.click(r, f"option:{o.pk}")
        self.click(r, "done")
        self.say("retirar cebola")
        item = self.current().cart.items.get()
        self.assertEqual(item.price, Decimal("24"))
        self.assertEqual(
            item.combination_details["customizations"][0]["option_name"], "Cheddar"
        )

    def test_delivery_fee_address_and_payment(self):
        DeliveryZone.objects.create(
            tenant=self.tenant, city="Itapevi", neighborhood="Centro", fee=Decimal("7")
        )
        self.add()
        for text in [
            "finalizar",
            "Jackson",
            "entrega",
            "Itapevi",
            "Centro",
            "Rua Um",
            "42",
            "SP",
            "06600000",
            "Casa B",
            "Portão azul",
        ]:
            self.say(text)
        r = self.say("debito")
        self.assertIn("47,00", r.text)
        self.assertIn("Portão azul", r.text)
        self.click(r, "confirm")
        order = Order.objects.get()
        self.assertEqual(order.delivery_fee, Decimal("7"))
        self.assertEqual(order.payment_method, "debit_card")
        self.assertEqual(order.delivery_complement, "Casa B")

    def test_delivery_outside_zone(self):
        DeliveryZone.objects.create(
            tenant=self.tenant, city="Itapevi", neighborhood="Centro", fee=Decimal("7")
        )
        self.add()
        for t in ["finalizar", "Jackson", "entrega", "Cotia"]:
            self.say(t)
        self.say("Centro")
        self.assertEqual(self.current().data["address_index"], 0)
        self.assertFalse(Order.objects.exists())

    def test_online_does_not_create_order_before_payment(self):
        c = self.online()
        self.assertFalse(Order.objects.exists())
        self.assertEqual(c.status, "issuing")
        self.assertTrue(c.reservations.exists())
        self.assertNotIn("24971563792", str(c.data))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal("10"))

    def test_online_reservation_blocks_other_cart(self):
        self.online()
        q = cart_service.quote(self.tenant, {"product_id": self.product.pk})
        with self.assertRaises(cart_service.CartError):
            inventory.check_stock([(q, 9)])

    @patch("apps.integrations.whatsapp_agent.checkout_payments.api_for")
    def test_verified_webhook_creates_paid_order_once(self, api):
        c = self.bind(self.online())
        api.return_value.get_payment.return_value = self.remote(c)
        e = self.event(c)
        apply_pix_event(c.pk, e)
        apply_pix_event(c.pk, e)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(WhatsAppOrderNotice.objects.count(), 2)
        self.assertIn("pago e validado", WhatsAppOrderNotice.objects.first().text)
        self.assertFalse(c.reservations.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal("8"))

    @patch("apps.integrations.whatsapp_agent.checkout_payments.api_for")
    def test_pending_remote_is_not_paid_even_with_received_event(self, api):
        c = self.bind(self.online())
        api.return_value.get_payment.return_value = self.remote(c, "PENDING")
        with self.assertRaises(BillingError):
            apply_pix_event(c.pk, self.event(c))
        self.assertFalse(Order.objects.exists())

    @patch("apps.integrations.whatsapp_agent.checkout_payments.api_for")
    def test_wrong_amount_or_reference_rejected(self, api):
        c = self.bind(self.online())
        e = self.event(c)
        for changes in [
            {"value": "1.00"},
            {"externalReference": "other"},
            {"billingType": "CREDIT_CARD"},
            {"id": "other"},
        ]:
            api.return_value.get_payment.return_value = self.remote(c, **changes)
            with self.assertRaises(BillingError):
                apply_pix_event(c.pk, e)
        self.assertFalse(Order.objects.exists())

    @patch("apps.integrations.whatsapp_agent.checkout_payments.api_for")
    def test_paid_snapshot_preserves_price_after_catalog_change(self, api):
        c = self.bind(self.online())
        Product.objects.filter(pk=self.product.pk).update(price=Decimal("30"))
        api.return_value.get_payment.return_value = self.remote(c)
        apply_pix_event(c.pk, self.event(c))
        self.assertEqual(Order.objects.get().total, Decimal("40"))

    @patch("apps.integrations.whatsapp_agent.checkout_payments.api_for")
    def test_pix_timeout_does_not_repost(self, api):
        c = self.online()
        api.return_value.find_payment.return_value = {"data": []}
        api.return_value.find_customer.return_value = {"data": []}
        api.return_value.create_customer.return_value = {"id": "cus_test"}
        api.return_value.create_payment.side_effect = BillingError("timeout")
        for _ in range(2):
            with self.assertRaises(BillingError):
                issue_pix(c.pk)
        self.assertEqual(api.return_value.create_payment.call_count, 1)
        self.assertFalse(Order.objects.exists())

    @patch("apps.integrations.whatsapp_agent.checkout_payments.api_for")
    def test_pix_recovers_existing_charge(self, api):
        c = self.online()
        c.status = "uncertain"
        c.save()
        remote = self.remote(c, "PENDING", id="pay_recovered")
        api.return_value.find_payment.return_value = {"data": [remote]}
        api.return_value.pix.return_value = {
            "payload": "000201",
            "encodedImage": "base64",
        }
        qr = issue_pix(c.pk)
        self.assertEqual(qr["payload"], "000201")
        api.return_value.create_payment.assert_not_called()
        c.refresh_from_db()
        self.assertEqual(c.provider_id, "pay_recovered")
        self.assertNotIn("document_encrypted", c.data)

    @patch("apps.integrations.whatsapp_agent.checkout_payments.api_for")
    def test_cancel_requires_provider_confirmation(self, api):
        c = self.bind(self.online())
        api.return_value.get_payment.return_value = self.remote(c, "PENDING")
        api.return_value.request.side_effect = BillingError("timeout")
        self.say("cancelar")
        c.refresh_from_db()
        self.assertEqual(c.status, "pending")
        self.assertTrue(c.reservations.exists())
        api.return_value.request.side_effect = None
        api.return_value.request.return_value = {"deleted": True}
        self.say("cancelar")
        c.refresh_from_db()
        self.assertEqual(c.status, "cancelled")
        self.assertFalse(c.reservations.exists())

    def test_interactive_replies(self):
        for payload in [
            {"buttonsResponseMessage": {"selectedButtonId": "wa:x:confirm"}},
            {
                "listResponseMessage": {
                    "singleSelectReply": {"selectedRowId": "wa:x:confirm"}
                }
            },
            {
                "interactiveResponseMessage": {
                    "nativeFlowResponseMessage": {"paramsJson": '{"id":"wa:x:confirm"}'}
                }
            },
        ]:
            self.assertEqual(extract_text({"message": payload}), "wa:x:confirm")
        self.assertEqual(
            extract_text(
                {
                    "message": {
                        "interactiveResponseMessage": {
                            "nativeFlowResponseMessage": {"paramsJson": "[1,2]"}
                        }
                    }
                }
            ),
            "",
        )

    @patch.object(
        TenantEvolutionClient, "_request", return_value={"key": {"id": "out"}}
    )
    def test_buttons_and_lists_payload(self, request):
        c = TenantEvolutionClient()
        c.send_choices("tenant", self.phone, [("a", "Confirmar"), ("b", "Alterar")])
        self.assertIn("sendButtons", request.call_args.args[1])
        c.send_choices("tenant", self.phone, [(str(i), f"Item {i}") for i in range(5)])
        self.assertIn("sendList", request.call_args.args[1])

    def test_optional_notes_accept_numbered_choice(self):
        r = self.say("novo pedido")
        self.click(r, f"product:{self.product.pk}")
        self.say("2")
        self.say("1")
        self.assertEqual(self.current().cart.items.get().notes, "")

    def test_human_handoff_preserves_cart(self):
        self.add()
        self.assertIsNone(self.say("quero falar com atendente"))
        self.assertEqual(self.current().cart.items.count(), 1)

    def test_other_tenant_button_is_rejected(self):
        r = self.say("novo pedido")
        old = r.choices[0][0]
        self.phone = "5511999999993"
        self.say("novo pedido")
        self.assertIn("etapa anterior", self.say(old).text)

    def test_small_change_amount_does_not_confirm(self):
        self.add()
        for t in ["finalizar", "Jackson", "retirada", "dinheiro"]:
            self.say(t)
        r = self.say("10,00")
        self.assertIn("40,00", r.text)
        self.assertEqual(self.current().step, "change")
        self.assertFalse(Order.objects.exists())

    @patch.object(
        TenantEvolutionClient, "_request", return_value={"key": {"id": "out"}}
    )
    def test_long_summary_is_split_without_losing_content(self, request):
        text = "Produto 1\n" * 700
        TenantEvolutionClient().send_text("tenant", self.phone, text)
        chunks = [c.args[2]["text"] for c in request.call_args_list]
        self.assertTrue(all(len(c) <= 3500 for c in chunks))
        self.assertEqual("\n".join(chunks).strip(), text.strip())

    @patch("apps.integrations.whatsapp_agent.checkout_payments.api_for")
    @override_settings(
        BILLING_ENABLED=True, ASAAS_API_KEY="test-key", ASAAS_WEBHOOK_TOKEN="t" * 40
    )
    def test_billing_task_routes_to_tenant_pix(self, api):
        from apps.billing.tasks import process_event

        c = self.bind(self.online())
        api.return_value.get_payment.return_value = self.remote(c)
        e = self.event(c)
        process_event(e.pk)
        e.refresh_from_db()
        self.assertIsNotNone(e.processed_at)
        self.assertEqual(Order.objects.count(), 1)

    @patch(
        "apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text",
        return_value="sent",
    )
    @override_settings(WHATSAPP_AGENT_ENABLED=True)
    def test_outbox_resends_only_unsent_notices(self, send):
        from apps.integrations.models import TenantWhatsAppAgent
        from apps.integrations.tasks import deliver_whatsapp_order_notices

        TenantWhatsAppAgent.objects.create(
            tenant=self.tenant, instance_name="tenant", instance_created=True
        )
        r = self.prepare("pix")
        self.click(r, "confirm")
        deliver_whatsapp_order_notices()
        deliver_whatsapp_order_notices()
        self.assertEqual(send.call_count, 2)

    @patch(
        "apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text",
        return_value="sent",
    )
    @patch("apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_choices")
    @override_settings(WHATSAPP_AGENT_ENABLED=True, WHATSAPP_AGENT_BUTTONS_ENABLED=True)
    def test_task_button_failure_keeps_text_flow(self, buttons, send):
        from apps.integrations.models import TenantWhatsAppAgent
        from apps.integrations.tasks import process_tenant_whatsapp_message
        from apps.integrations.whatsapp.client import EvolutionError

        buttons.side_effect = EvolutionError("unavailable")
        a = TenantWhatsAppAgent.objects.create(
            tenant=self.tenant,
            instance_name="tenant",
            ai_enabled=True,
            instance_created=True,
        )
        result = process_tenant_whatsapp_message(
            a.pk, "new1", self.phone, "novo pedido"
        )
        self.assertEqual(result, "answered:checkout")
        self.assertIn("1.", send.call_args.args[2])

    @patch("apps.integrations.whatsapp_agent.checkout_payments.api_for")
    def test_maintenance_never_releases_paid_without_webhook(self, api):
        from datetime import timedelta
        from django.utils import timezone
        from apps.integrations.tasks import maintain_whatsapp_checkouts

        c = self.bind(self.online())
        c.expires_at = timezone.now() - timedelta(minutes=1)
        c.save()
        api.return_value.get_payment.return_value = self.remote(c)
        maintain_whatsapp_checkouts()
        self.assertFalse(Order.objects.exists())
        self.assertTrue(c.reservations.exists())
        api.return_value.request.assert_not_called()


from django.test import TransactionTestCase, skipUnlessDBFeature


@skipUnlessDBFeature("has_select_for_update")
class WhatsAppCheckoutConcurrencyTests(TransactionTestCase):
    setUp = WhatsAppCheckoutTests.setUp
    say = WhatsAppCheckoutTests.say
    click = WhatsAppCheckoutTests.click
    current = WhatsAppCheckoutTests.current
    add = WhatsAppCheckoutTests.add
    prepare = WhatsAppCheckoutTests.prepare

    def test_parallel_confirmation_produces_one_order(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections

        r = self.prepare("pix")
        action = next(k for k, _ in r.choices if k.endswith(":confirm"))
        barrier = Barrier(2)

        def confirm():
            close_old_connections()
            try:
                tenant = Tenant.objects.get(pk=self.tenant.pk)
                barrier.wait(timeout=10)
                return handle_checkout(tenant, self.phone, "same-confirmation", action)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(confirm), pool.submit(confirm)]
            for future in futures:
                future.result(timeout=20)
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal("8"))
