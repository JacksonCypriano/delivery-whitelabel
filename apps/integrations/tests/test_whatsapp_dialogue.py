from decimal import Decimal
from unittest.mock import patch, Mock

from django.test import TestCase, override_settings
from apps.integrations.tests import test_whatsapp_checkout as fixtures
from apps.integrations.whatsapp_agent.dialogue import (
    local_plan,
    validated_plan,
    model_plan,
)
from apps.integrations.whatsapp_agent.checkout import handle_checkout
from apps.orders import cart_service as rules
from apps.orders.models import Order
from apps.stores.models import Product, Category


@override_settings(WHATSAPP_AGENT_OLLAMA_ENABLED=False)
class DialogueTests(TestCase):
    setUp = fixtures.WhatsAppCheckoutTests.setUp
    say = fixtures.WhatsAppCheckoutTests.say
    click = fixtures.WhatsAppCheckoutTests.click
    current = fixtures.WhatsAppCheckoutTests.current
    add = fixtures.WhatsAppCheckoutTests.add
    prepare = fixtures.WhatsAppCheckoutTests.prepare

    def drink(self, name="Coca-Cola 2L"):
        cat, _ = Category.objects.get_or_create(tenant=self.tenant, name="Bebidas")
        return Product.objects.create(
            tenant=self.tenant, category=cat, name=name, price=Decimal("10"), stock=10
        )

    def approve(self, result):
        return self.click(result, "dialogue_apply")

    def test_multi_item_sentence_keeps_queue_and_notes(self):
        coca = self.drink()
        r = self.say("manda dois X Burger sem cebola e uma Coca-Cola 2L")
        self.assertIn("2x X Burger", r.text)
        self.assertIn("1x Coca-Cola 2L", r.text)
        self.assertEqual(self.current().cart.items.count(), 0)
        r = self.approve(r)
        self.click(r, "dialogue_keep_note")
        self.say("sem observacao")
        items = self.current().cart.items
        self.assertEqual(items.count(), 2)
        self.assertEqual(items.get(product=self.product).quantity, 2)
        self.assertEqual(items.get(product=self.product).notes, "sem cebola")
        self.assertEqual(items.get(product=coca).quantity, 1)

    def test_product_typo_is_previewed(self):
        r = self.say("manda um X Burgr")
        self.assertIn("1x X Burger", r.text)
        self.assertEqual(self.current().cart.items.count(), 0)

    def test_ambiguous_coca_does_not_pick_size(self):
        self.drink()
        self.drink("Coca-Cola Lata")
        r = self.say("manda uma coca")
        self.assertIn("confirmar o produto", r.text)
        self.assertFalse(self.current().cart.items.exists())

    def test_replace_validated_before_removing_original(self):
        juice = self.drink("Suco de Laranja")
        self.add()
        r = self.say("troca item 1 por Suco de Laranja")
        self.assertEqual(self.current().cart.items.get().product_id, self.product.pk)
        self.approve(r)
        self.say("sem observacao")
        self.assertEqual(self.current().cart.items.get().product_id, juice.pk)
        self.assertEqual(self.current().cart.items.get().quantity, 2)

    def test_quantity_change_is_validated(self):
        self.add()
        r = self.say("deixa item 1 com tres unidades")
        self.approve(r)
        self.assertEqual(self.current().cart.items.get().quantity, 3)

    def test_more_one_preserves_options_and_notes(self):
        self.add("retirar cebola")
        self.approve(self.say("mais um"))
        item = self.current().cart.items.get()
        self.assertEqual(item.quantity, 3)
        self.assertEqual(item.notes, "retirar cebola")

    def test_remove_last_is_previewed(self):
        self.add()
        r = self.say("tira o ultimo")
        self.assertTrue(self.current().cart.items.exists())
        self.approve(r)
        self.assertFalse(self.current().cart.items.exists())

    def test_notes_one_unit_splits_line_and_preserves_total(self):
        self.add()
        r = self.say("sem cebola")
        r = self.click(r, "dialogue_note_one")
        self.approve(r)
        items = list(self.current().cart.items.all())
        self.assertEqual(len(items), 2)
        self.assertEqual(sum(i.quantity for i in items), 2)
        self.assertEqual(sum(i.get_total_price() for i in items), Decimal("40"))
        self.assertEqual(sum(i.quantity for i in items if i.notes), 1)

    def test_notes_all_units(self):
        self.add()
        r = self.say("sem cebola")
        self.approve(self.click(r, "dialogue_note_all"))
        self.assertEqual(self.current().cart.items.get().notes, "sem cebola")

    def test_question_during_quantity_resumes_original_choices(self):
        r = self.say("novo pedido")
        self.click(r, f"product:{self.product.pk}")
        r = self.say("qual o horario de funcionamento?")
        self.assertEqual(self.current().step, "quantity")
        r = self.click(r, "dialogue_resume")
        self.assertIn("Quantas unidades", r.text)
        self.click(r, "qty:2")
        self.assertEqual(self.current().step, "notes")

    def test_question_during_address_does_not_become_street(self):
        self.add()
        for text in ["finalizar", "Jackson", "entrega"]:
            self.say(text)
        r = self.say("aceita cartao?")
        self.assertNotIn("delivery_city", self.current().data)
        self.click(r, "dialogue_resume")
        self.say("Itapevi")
        self.assertEqual(self.current().data["delivery_city"], "Itapevi")

    def test_question_during_final_review_cannot_confirm(self):
        r = self.prepare("pix")
        question = self.say("qual o endereco da loja?")
        self.assertFalse(Order.objects.exists())
        r = self.click(question, "dialogue_resume")
        self.click(r, "confirm")
        self.assertEqual(Order.objects.count(), 1)

    def test_declining_proposal_does_not_mutate(self):
        self.add()
        r = self.say("tira o ultimo")
        self.click(r, "dialogue_discard")
        self.assertEqual(self.current().cart.items.count(), 1)

    def test_stale_proposal_rechecks_cart_fingerprint(self):
        self.add()
        r = self.say("mais um")
        self.current().cart.items.update(quantity=4)
        self.approve(r)
        self.assertEqual(self.current().cart.items.get().quantity, 4)

    def test_undo_restores_previous_cart(self):
        self.add()
        self.approve(self.say("mais um"))
        r = self.say("desfazer")
        self.click(r, "dialogue_undo_confirm")
        self.assertEqual(self.current().cart.items.get().quantity, 2)

    def test_undo_validates_stock(self):
        self.add()
        self.approve(self.say("tira o ultimo"))
        Product.objects.filter(pk=self.product.pk).update(stock=0)
        r = self.say("desfazer")
        r = self.click(r, "dialogue_undo_confirm")
        self.assertIn("Estoque insuficiente", r.text)
        self.assertEqual(self.current().cart.items.count(), 0)

    def test_suggestion_never_auto_adds(self):
        self.drink()
        r = self.add()
        result = self.click(r, "dialogue_suggest")
        self.assertIn("Coca-Cola", result.text)
        self.assertEqual(self.current().cart.items.count(), 1)
        self.click(result, "dialogue_no_suggest")
        self.assertTrue(self.current().data["dialogue_suggestions_declined"])

    def test_unavailable_and_foreign_products_cannot_be_model_actions(self):
        from apps.tenants.models import Tenant

        tenant = Tenant.objects.create(
            name="Other", slug="other", whatsapp_number="5511999999988"
        )
        category = Category.objects.create(tenant=tenant, name="Food")
        foreign = Product.objects.create(
            tenant=tenant, category=category, name="Food", price=1
        )
        self.say("novo pedido")
        with self.assertRaises(rules.CartError):
            validated_plan(
                self.current(), [{"op": "add", "product_id": foreign.pk, "quantity": 1}]
            )
        Product.objects.filter(pk=self.product.pk).update(is_available=False)
        with self.assertRaises(rules.CartError):
            validated_plan(
                self.current(),
                [{"op": "add", "product_id": self.product.pk, "quantity": 1}],
            )

    def test_model_cannot_confirm_pay_or_change_prices(self):
        self.add()
        for op in ["confirm", "pay", "set_price", "refund", "sql"]:
            with self.assertRaises(rules.CartError):
                validated_plan(self.current(), [{"op": op}])
        result = validated_plan(
            self.current(),
            [
                {
                    "op": "add",
                    "product_id": self.product.pk,
                    "quantity": 1,
                    "price": 0.01,
                }
            ],
        )
        self.assertNotIn("price", result[0])

    def test_hypothetical_question_does_not_change_cart(self):
        self.add()
        self.say("quanto ficaria se eu colocar mais um?")
        self.assertEqual(self.current().cart.items.get().quantity, 2)
        self.assertNotIn("dialogue_proposal", self.current().data)

    def test_allergy_never_promises_safety(self):
        self.add()
        r = self.say("tenho alergia a leite, posso comer?")
        self.assertIn("contaminação", r.text)
        self.assertIn("atendente", r.text)
        self.assertEqual(self.current().cart.items.get().notes, "")

    def test_nlu_disabled_uses_no_network(self):
        self.say("novo pedido")
        with patch(
            "apps.integrations.whatsapp_agent.dialogue.requests.Session"
        ) as session:
            self.assertIsNone(model_plan(self.current(), "qualquer coisa"))
            session.assert_not_called()

    def test_change_payment_invalidates_previous_review(self):
        self.prepare("pix")
        r = self.say("quero pagar de outra forma")
        self.assertEqual(self.current().step, "payment")
        self.assertEqual(self.current().snapshot, {})
        r = self.say("vou pagar em dinheiro")
        self.assertEqual(self.current().step, "change")

    def test_question_during_proposal_restores_proposal_buttons(self):
        self.add()
        self.say("mais um")
        self.say("qual o horario?")
        r = self.say("continuar")
        self.assertTrue(any(k.endswith(":dialogue_apply") for k, _ in r.choices))
        self.approve(r)
        self.assertEqual(self.current().cart.items.get().quantity, 3)

    def test_more_one_with_multiple_products_needs_clarification(self):
        self.add()
        self.drink()
        r = self.say("quero uma Coca-Cola 2L")
        self.approve(r)
        self.say("sem observacao")
        r = self.say("mais um")
        self.assertIn("qual produto", r.text)
        self.assertFalse(self.current().data.get("dialogue_proposal"))

    def test_skip_queued_item_preserves_following_item(self):
        self.drink()
        r = self.say("manda um X Burger e uma Coca-Cola 2L")
        self.approve(r)
        r = self.say("pular item")
        self.assertIn("Coca-Cola", r.text)
        self.say("sem observacao")
        self.assertEqual(self.current().cart.items.count(), 1)
        self.assertEqual(self.current().cart.items.get().name, "Coca-Cola 2L")

    @override_settings(
        WHATSAPP_AGENT_OLLAMA_ENABLED=True, WHATSAPP_AGENT_NLU_ENABLED=True
    )
    def test_model_output_validated_and_never_directly_applied(self):
        import json

        self.add()
        item = self.current().cart.items.get()
        response = Mock(status_code=200)
        response.iter_content.return_value = [
            json.dumps(
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "ops": [
                                    {
                                        "op": "quantity",
                                        "item_id": item.pk,
                                        "quantity": 3,
                                        "price": 0,
                                    }
                                ]
                            }
                        )
                    }
                }
            ).encode()
        ]
        with patch(
            "apps.integrations.whatsapp_agent.dialogue.requests.Session"
        ) as session:
            session.return_value.__enter__.return_value.post.return_value.__enter__.return_value = (
                response
            )
            plan = model_plan(self.current(), "seriam tres desse aqui")
        self.assertEqual(plan, [{"op": "quantity", "item_id": item.pk, "quantity": 3}])
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    @override_settings(
        WHATSAPP_AGENT_OLLAMA_ENABLED=True, WHATSAPP_AGENT_NLU_ENABLED=True
    )
    def test_model_malformed_and_timeout_fall_back(self):
        import requests

        self.add()
        response = Mock(status_code=200)
        response.iter_content.return_value = [b"not json"]
        with patch(
            "apps.integrations.whatsapp_agent.dialogue.requests.Session"
        ) as session:
            client = session.return_value.__enter__.return_value
            client.post.return_value.__enter__.return_value = response
            self.assertIsNone(model_plan(self.current(), "teste"))
            client.post.side_effect = requests.Timeout()
            self.assertIsNone(model_plan(self.current(), "teste"))
        self.assertEqual(self.current().cart.items.get().quantity, 2)

    def test_cart_correction_during_payment_returns_to_cart_review(self):
        self.prepare("pix")
        self.say("trocar pagamento")
        r = self.say("deixa item 1 com tres unidades")
        self.assertEqual(self.current().cart.items.get().quantity, 2)
        self.approve(r)
        self.assertEqual(self.current().cart.items.get().quantity, 3)
        self.assertEqual(self.current().step, "menu")
        self.assertEqual(self.current().snapshot, {})
        self.assertFalse(Order.objects.exists())

    def test_quantity_accepts_portuguese_number(self):
        self.say("novo pedido")
        self.say("X Burger")
        self.say("duas")
        self.say("sem observacao")
        self.assertEqual(self.current().cart.items.get().quantity, 2)
