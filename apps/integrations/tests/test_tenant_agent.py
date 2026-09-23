import json
from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.integrations.models import (
    TenantWhatsAppAgent,
    TenantWhatsAppConversation,
)
from apps.integrations.tasks import process_tenant_whatsapp_message
from apps.integrations.whatsapp_agent.connection import (
    apply_connection_webhook,
    get_or_create_agent,
    monitor_agent,
)
from apps.integrations.whatsapp_agent.knowledge import answer_from_store, normalize, product_url
from apps.orders.models import Order
from apps.orders.services import build_whatsapp_message
from apps.orders.whatsapp_marker import extract_order_id
from apps.stores.models import (
    Category,
    CustomizationGroup,
    CustomizationGroupLabel,
    CustomizationOption,
    Product,
)
from apps.tenants.models import BusinessHour, DeliveryZone, Tenant


BASE_AGENT_SETTINGS = dict(
    WHATSAPP_AGENT_ENABLED=True,
    WHATSAPP_AGENT_WEBHOOK_TOKEN="t" * 48,
    WHATSAPP_AGENT_WEBHOOK_URL="https://vemdedelivery.com.br/integracoes/evolution/tenant-webhook/",
    WHATSAPP_AGENT_AUTO_RECONNECT=True,
    WHATSAPP_AGENT_MAX_RECONNECT_ATTEMPTS=3,
    WHATSAPP_AGENT_ORDER_PAUSE_MINUTES=30,
    WHATSAPP_AGENT_MANUAL_PAUSE_MINUTES=60,
    WHATSAPP_AGENT_CONTEXT_TIMEOUT_MINUTES=45,
    WHATSAPP_AGENT_OLLAMA_ENABLED=False,
)


@override_settings(**BASE_AGENT_SETTINGS)
class TenantWhatsAppAgentTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Bella Massa",
            slug="bella-massa",
            whatsapp_number="5511999999991",
            pickup_address="Rua das Flores",
            pickup_number="100",
            pickup_neighborhood="Centro",
            pickup_city="Itapevi",
            pickup_zip_code="06600-000",
        )
        self.other = Tenant.objects.create(
            name="Outra Loja",
            slug="outra-loja",
            whatsapp_number="5511999999992",
        )
        self.category = Category.objects.create(
            tenant=self.tenant, name="Bebidas"
        )
        self.product = Product.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Coca-Cola 2L",
            price=Decimal("14.90"),
            is_available=True,
        )
        DeliveryZone.objects.create(
            tenant=self.tenant,
            city="Itapevi",
            neighborhood="Jardim Paulista",
            fee=Decimal("7.00"),
            is_active=True,
        )

    def test_instance_is_isolated_per_tenant(self):
        first = get_or_create_agent(self.tenant)
        second = get_or_create_agent(self.other)
        self.assertNotEqual(first.instance_name, second.instance_name)
        self.assertEqual(first.tenant_id, self.tenant.pk)
        self.assertEqual(second.tenant_id, self.other.pk)

    def test_product_answer_uses_only_current_tenant(self):
        other_category = Category.objects.create(tenant=self.other, name="Bebidas")
        Product.objects.create(
            tenant=self.other,
            category=other_category,
            name="Guaraná secreto",
            price=Decimal("1.00"),
        )
        answer = answer_from_store(self.tenant, "Vocês têm Coca-Cola 2L?")
        self.assertEqual(answer.intent, "product")
        self.assertIn("Coca-Cola 2L", " ".join(answer.facts))
        self.assertNotIn("Guaraná secreto", " ".join(answer.facts))

    def test_product_plural_and_category_are_understood(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant, category=burgers, name="Bacon Especial",
            price=Decimal("31.90"), is_available=True,
        )
        answer = answer_from_store(self.tenant, "Quais hambúrgueres vocês têm?")
        self.assertEqual(answer.intent, "product")
        self.assertIn("Bacon Especial", " ".join(answer.facts))

    def test_product_answer_has_direct_agent_link(self):
        answer = answer_from_store(self.tenant, "Tem Coca-Cola 2L?")
        expected = product_url(self.tenant, self.product)
        self.assertIn(expected, answer.fallback)
        self.assertIn("source=whatsapp-agent", expected)

    def test_whatsapp_abbreviations_are_normalized(self):
        self.assertEqual(
            normalize("vcs tm refri? qnt custa hj?"),
            "voces tem bebida quanto custa hoje",
        )
        self.assertEqual(normalize("aceita piks?"), "aceita pix")
        self.assertEqual(
            normalize("vocês voces vcs"),
            "voces voces voces",
        )

    def test_product_typo_is_understood_and_specific_price_returns_one_item(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        bacon = Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Bacon",
            price=Decimal("31.90"), is_available=True,
        )
        Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Clássico",
            price=Decimal("24.90"), is_available=True,
        )
        answer = answer_from_store(
            self.tenant, "qnt custa o hambuger bacom?"
        )
        self.assertEqual(answer.intent, "product")
        self.assertIn("Hambúrguer Bacon", answer.fallback)
        self.assertIn("R$ 31,90", answer.fallback)
        self.assertNotIn("Hambúrguer Clássico", answer.fallback)
        self.assertIn(product_url(self.tenant, bacon), answer.fallback)

    def test_product_link_intent_returns_only_requested_product(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        bacon = Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Bacon",
            price=Decimal("31.90"), is_available=True,
        )
        Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Clássico",
            price=Decimal("24.90"), is_available=True,
        )
        answer = answer_from_store(
            self.tenant, "me manda o lik do hamburgue bacon"
        )
        self.assertEqual(answer.intent, "product")
        self.assertIn(product_url(self.tenant, bacon), answer.fallback)
        self.assertNotIn("Hambúrguer Clássico", answer.fallback)
        self.assertIn("Aqui está", answer.fallback)

    def test_product_list_uses_blank_lines_between_items(self):
        drinks = self.category
        Product.objects.create(
            tenant=self.tenant, category=drinks, name="Guaraná 350 ml",
            price=Decimal("7.50"), is_available=True,
        )
        answer = answer_from_store(self.tenant, "qauis bebids vcs tem?")
        self.assertEqual(answer.intent, "product")
        self.assertIn("\n\n", answer.fallback)
        self.assertIn("Coca-Cola 2L", answer.fallback)
        self.assertIn("Guaraná 350 ml", answer.fallback)

    def test_product_list_question_uses_options_intro(self):
        Product.objects.create(
            tenant=self.tenant, category=self.category, name="Guaraná 350 ml",
            price=Decimal("7.50"), is_available=True,
        )
        answer = answer_from_store(self.tenant, "Quais bebidas vcs têm?")
        self.assertEqual(answer.intent, "product")
        self.assertTrue(answer.fallback.startswith("Temos estas opções"))
        self.assertFalse(answer.fallback.startswith("Temos sim"))

    def test_ambiguous_product_price_does_not_pick_random_variant(self):
        Product.objects.create(
            tenant=self.tenant, category=self.category, name="Coca-Cola Zero 2L",
            price=Decimal("15.90"), is_available=True,
        )
        answer = answer_from_store(self.tenant, "qto custa coca cola?")
        self.assertEqual(answer.intent, "product")
        self.assertIn("Coca-Cola 2L", answer.fallback)
        self.assertIn("Coca-Cola Zero 2L", answer.fallback)

    def test_delivery_typo_and_abbreviation_are_understood(self):
        answer = answer_from_store(
            self.tenant, "qnt fica a entrga pro Jardim Paulsta em Itapevi?"
        )
        self.assertEqual(answer.intent, "delivery_fee")
        self.assertIn("R$ 7,00", answer.fallback)
        self.assertIn("Jardim Paulista, Itapevi", answer.fallback)

    def test_delivery_without_city_asks_city_before_fee(self):
        DeliveryZone.objects.create(
            tenant=self.tenant, city="Cotia", neighborhood="Centro",
            fee=Decimal("12.00"), is_active=True,
        )
        DeliveryZone.objects.create(
            tenant=self.tenant, city="Itapevi", neighborhood="Centro",
            fee=Decimal("5.00"), is_active=True,
        )
        answer = answer_from_store(
            self.tenant, "qnt fica a entrega pro Centro?"
        )
        self.assertEqual(answer.intent, "delivery")
        self.assertIn("cidade", answer.fallback.lower())
        self.assertEqual(answer.context.get("neighborhood"), "Centro")
        self.assertNotIn("R$ 5,00", answer.fallback)
        self.assertNotIn("R$ 12,00", answer.fallback)

    def test_delivery_followup_city_completes_pending_neighborhood(self):
        DeliveryZone.objects.create(
            tenant=self.tenant, city="Itapevi", neighborhood="Centro",
            fee=Decimal("5.00"), is_active=True,
        )
        first = answer_from_store(self.tenant, "qnt fica a entrega pro Centro?")
        answer = answer_from_store(self.tenant, "Itapevi", context=first.context)
        self.assertEqual(answer.intent, "delivery_fee")
        self.assertIn("R$ 5,00", answer.fallback)
        self.assertIn("Centro, Itapevi", answer.fallback)

    def test_delivery_context_does_not_trap_new_explicit_intents(self):
        today = timezone.localdate().weekday()
        BusinessHour.objects.create(
            tenant=self.tenant, weekday=today, is_closed=False,
            opening_time=time(11, 0), closing_time=time(23, 0),
        )
        context = {
            "intent": "delivery_fee",
            "city": "Itapevi",
            "neighborhood": "Jardim Paulista",
        }

        address = answer_from_store(self.tenant, "ond vcs fika?", context=context)
        self.assertEqual(address.intent, "address")
        self.assertIn("Rua das Flores", address.fallback)

        hours = answer_from_store(self.tenant, "q hrs fehca hj?", context=context)
        self.assertEqual(hours.intent, "hours")
        self.assertIn("23:00", hours.fallback)

        payment = answer_from_store(self.tenant, "vcs aceita piks?", context=context)
        self.assertEqual(payment.intent, "payment")
        self.assertIn("Pix", payment.fallback)

    def test_delivery_followup_reuses_city_for_next_neighborhood(self):
        DeliveryZone.objects.create(
            tenant=self.tenant, city="Itapevi", neighborhood="Jardim Rainha",
            fee=Decimal("9.00"), is_active=True,
        )
        context = {
            "intent": "delivery_fee",
            "city": "Itapevi",
            "neighborhood": "Jardim Paulista",
        }
        answer = answer_from_store(
            self.tenant, "e pro Jardim Rainha?", context=context
        )
        self.assertEqual(answer.intent, "delivery_fee")
        self.assertIn("R$ 9,00", answer.fallback)
        self.assertIn("Jardim Rainha, Itapevi", answer.fallback)

    def test_address_informal_typo_is_understood(self):
        answer = answer_from_store(self.tenant, "ond vcs fika?")
        self.assertEqual(answer.intent, "address")
        self.assertIn("Rua das Flores", answer.fallback)

    def test_payment_typo_is_understood(self):
        answer = answer_from_store(self.tenant, "vcs aceita piks?")
        self.assertEqual(answer.intent, "payment")
        self.assertIn("Pix", answer.fallback)

    def test_payment_does_not_announce_online_when_not_released(self):
        answer = answer_from_store(self.tenant, "vcs aceita piks?")
        self.assertEqual(answer.intent, "payment")
        self.assertIn("Na entrega ou retirada", answer.fallback)
        self.assertNotIn("Online:", answer.fallback)

    def test_payment_does_not_announce_online_when_release_exists_but_subaccount_is_not_ready(self):
        from apps.billing.models import TenantPaymentAccount

        self.tenant.online_payments_allowed = True
        self.tenant.save(update_fields=["online_payments_allowed"])
        TenantPaymentAccount.objects.create(
            tenant=self.tenant,
            enabled=True,
            terms_accepted=True,
            status=TenantPaymentAccount.Status.PENDING,
        )

        answer = answer_from_store(self.tenant, "aceita pix?")
        self.assertEqual(answer.intent, "payment")
        self.assertNotIn("Online:", answer.fallback)

    def test_payment_announces_online_only_when_subaccount_is_ready(self):
        from apps.billing.models import TenantPaymentAccount

        self.tenant.online_payments_allowed = True
        self.tenant.save(update_fields=["online_payments_allowed"])
        account = TenantPaymentAccount(
            tenant=self.tenant,
            enabled=True,
            terms_accepted=True,
            status=TenantPaymentAccount.Status.APPROVED,
            provider_account_id="acc_test",
        )
        account.set_api_key("subaccount-test-key")
        account.save()
        self.tenant.refresh_from_db()

        answer = answer_from_store(self.tenant, "aceita pix?")
        self.assertEqual(answer.intent, "payment")
        self.assertIn("Online: Pix ou cartão de crédito", answer.fallback)

    def test_payment_text_respects_fulfillment_mode(self):
        from apps.tenants.choices import FulfillmentMode

        self.tenant.fulfillment_mode = FulfillmentMode.PICKUP_ONLY
        self.tenant.save(update_fields=["fulfillment_mode"])
        answer = answer_from_store(self.tenant, "formas de pagamento?")
        self.assertIn("Na retirada", answer.fallback)
        self.assertNotIn("Na entrega ou retirada", answer.fallback)

    def test_hours_typo_and_abbreviation_are_understood(self):
        today = timezone.localdate().weekday()
        BusinessHour.objects.create(
            tenant=self.tenant, weekday=today, is_closed=False,
            opening_time=time(11, 0), closing_time=time(23, 0),
        )
        answer = answer_from_store(self.tenant, "q hrs fehca hj?")
        self.assertEqual(answer.intent, "hours")
        self.assertIn("23:00", answer.fallback)

    def test_product_deep_link_opens_catalog_product(self):
        response = self.client.get(
            f"/produto/{self.product.slug}/",
            HTTP_HOST=f"{self.tenant.slug}.lvh.me",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-open-product-slug="{self.product.slug}"')
        self.assertContains(response, f'data-product-slug="{self.product.slug}"')

    def test_context_expires_after_inactivity(self):
        from apps.integrations.whatsapp_agent.conversations import active_context

        row = TenantWhatsAppConversation.objects.create(
            tenant=self.tenant,
            phone_number="5511988887766",
            context={"intent": "product", "product_ids": [self.product.pk]},
            context_updated_at=timezone.now() - timedelta(minutes=46),
        )
        self.assertEqual(active_context(row), {})
        row.refresh_from_db()
        self.assertEqual(row.context, {})
        self.assertIsNone(row.context_updated_at)

    def test_today_closing_time_is_concise(self):
        today = timezone.localdate().weekday()
        BusinessHour.objects.create(
            tenant=self.tenant, weekday=today, is_closed=False,
            opening_time=time(11, 0), closing_time=time(23, 0),
        )
        answer = answer_from_store(self.tenant, "Que horas fecha hoje?")
        self.assertEqual(answer.intent, "hours")
        self.assertIn("23:00", answer.fallback)
        self.assertNotIn("Segunda-feira:", answer.fallback)

    def test_delivery_fee_answer_uses_delivery_zone(self):
        answer = answer_from_store(
            self.tenant, "Qual o valor da entrega no Jardim Paulista em Itapevi?"
        )
        self.assertEqual(answer.intent, "delivery_fee")
        self.assertIn("R$ 7,00", answer.fallback)
        self.assertIn("A entrega para", answer.fallback)

    def test_order_message_has_deterministic_marker(self):
        order = Order.objects.create(
            tenant=self.tenant,
            customer_name="Cliente",
            customer_phone="11988887777",
            total=Decimal("14.90"),
            subtotal=Decimal("14.90"),
            delivery_type="pickup",
            payment_method="pix",
            payment_flow="in_person",
            whatsapp_opened_at=timezone.now(),
        )
        message = build_whatsapp_message(order)
        self.assertIn("VDD-ORDER:", message)
        self.assertEqual(extract_order_id(message), order.pk)
        self.assertNotIn(str(order.public_token), message)
        self.assertFalse(message.startswith("_Ref. VemDeDelivery:"))

    def test_extract_order_id_accepts_legacy_italic_marker(self):
        order = Order.objects.create(
            tenant=self.tenant,
            customer_name="Cliente",
            customer_phone="11988887777",
            total=Decimal("14.90"),
            subtotal=Decimal("14.90"),
            delivery_type="pickup",
            payment_method="pix",
            payment_flow="in_person",
            whatsapp_opened_at=timezone.now(),
        )
        from apps.orders.whatsapp_marker import build_order_marker

        legacy = f"_Ref. VemDeDelivery: {build_order_marker(order)}_\n*Pedido*"
        self.assertEqual(extract_order_id(legacy), order.pk)

    @patch("apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text")
    def test_order_marker_never_triggers_agent_reply(self, send_text):
        agent = get_or_create_agent(self.tenant)
        agent.ai_enabled = True
        agent.instance_created = True
        agent.status = TenantWhatsAppAgent.Status.OPEN
        agent.save()
        order = Order.objects.create(
            tenant=self.tenant,
            customer_name="Cliente",
            customer_phone="11988887777",
            total=Decimal("14.90"),
            subtotal=Decimal("14.90"),
            delivery_type="pickup",
            payment_method="pix",
            payment_flow="in_person",
            whatsapp_opened_at=timezone.now(),
        )
        result = process_tenant_whatsapp_message(
            agent.pk,
            "MSG-ORDER",
            "5511988887777",
            build_whatsapp_message(order),
        )
        self.assertEqual(result, "order-ignored")
        send_text.assert_not_called()
        state = TenantWhatsAppConversation.objects.get(
            tenant=self.tenant, phone_number="5511988887777"
        )
        self.assertEqual(state.pause_reason, TenantWhatsAppConversation.PauseReason.ORDER)
        self.assertGreater(state.ai_paused_until, timezone.now())

    @patch("apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text")
    def test_normal_question_is_answered(self, send_text):
        send_text.return_value = "OUT-1"
        agent = get_or_create_agent(self.tenant)
        agent.ai_enabled = True
        agent.instance_created = True
        agent.status = TenantWhatsAppAgent.Status.OPEN
        agent.save()
        result = process_tenant_whatsapp_message(
            agent.pk, "IN-1", "5511988887777", "Tem Coca-Cola 2L?"
        )
        self.assertEqual(result, "answered:product")
        args = send_text.call_args.args
        self.assertEqual(args[0], agent.instance_name)
        self.assertEqual(args[1], "5511988887777")
        self.assertIn("Coca-Cola 2L", args[2])

    def test_logout_requires_new_pairing(self):
        agent = get_or_create_agent(self.tenant)
        agent.instance_created = True
        agent.status = TenantWhatsAppAgent.Status.OPEN
        agent.save()
        apply_connection_webhook(agent, {"state": "close", "statusReason": 401})
        agent.refresh_from_db()
        self.assertEqual(agent.status, TenantWhatsAppAgent.Status.PAIRING)
        self.assertTrue(agent.requires_pairing)

    def test_transient_drop_restarts_without_pairing(self):
        agent = get_or_create_agent(self.tenant)
        agent.instance_created = True
        agent.status = TenantWhatsAppAgent.Status.CLOSED
        agent.save()
        client = Mock()
        client.status.return_value = "close"
        monitor_agent(agent, client=client)
        agent.refresh_from_db()
        client.restart.assert_called_once_with(agent.instance_name)
        self.assertEqual(agent.reconnect_attempts, 1)
        self.assertFalse(agent.requires_pairing)

    @patch("apps.integrations.tasks.process_tenant_whatsapp_message.delay")
    def test_webhook_queues_only_customer_direct_message(self, delay):
        agent = get_or_create_agent(self.tenant)
        agent.instance_created = True
        agent.ai_enabled = True
        agent.save()
        payload = {
            "event": "MESSAGES_UPSERT",
            "instance": agent.instance_name,
            "data": {
                "key": {
                    "remoteJid": "5511988887777@s.whatsapp.net",
                    "fromMe": False,
                    "id": "IN-WEBHOOK-1",
                },
                "message": {"conversation": "Qual o endereço?"},
            },
        }
        response = self.client.post(
            "/integracoes/evolution/tenant-webhook/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_VDD_WEBHOOK_TOKEN="t" * 48,
        )
        self.assertEqual(response.status_code, 202)
        delay.assert_called_once_with(
            agent.pk, "IN-WEBHOOK-1", "5511988887777", "Qual o endereço?", "text"
        )

    def test_manual_store_message_pauses_conversation(self):
        agent = get_or_create_agent(self.tenant)
        agent.instance_created = True
        agent.ai_enabled = True
        agent.save()
        payload = {
            "event": "MESSAGES_UPSERT",
            "instance": agent.instance_name,
            "data": {
                "key": {
                    "remoteJid": "5511988887777@s.whatsapp.net",
                    "fromMe": True,
                    "id": "STORE-1",
                },
                "message": {"conversation": "Olá, sou da loja."},
            },
        }
        response = self.client.post(
            "/integracoes/evolution/tenant-webhook/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_VDD_WEBHOOK_TOKEN="t" * 48,
        )
        self.assertEqual(response.status_code, 202)
        state = TenantWhatsAppConversation.objects.get(
            tenant=self.tenant, phone_number="5511988887777"
        )
        self.assertEqual(state.pause_reason, TenantWhatsAppConversation.PauseReason.MANUAL)
        self.assertGreater(state.ai_paused_until, timezone.now())

    def test_group_message_is_ignored(self):
        agent = get_or_create_agent(self.tenant)
        agent.instance_created = True
        agent.ai_enabled = True
        agent.save()
        payload = {
            "event": "MESSAGES_UPSERT",
            "instance": agent.instance_name,
            "data": {
                "key": {
                    "remoteJid": "123456@g.us",
                    "fromMe": False,
                    "id": "GROUP-1",
                },
                "message": {"conversation": "Oi"},
            },
        }
        response = self.client.post(
            "/integracoes/evolution/tenant-webhook/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_VDD_WEBHOOK_TOKEN="t" * 48,
        )
        self.assertEqual(response.status_code, 204)


    def test_fulfillment_answers_delivery_and_pickup_from_tenant_mode(self):
        from apps.tenants.choices import FulfillmentMode

        self.tenant.fulfillment_mode = FulfillmentMode.PICKUP_ONLY
        self.tenant.save(update_fields=["fulfillment_mode"])
        delivery = answer_from_store(self.tenant, "vcs fazem entrega?")
        self.assertEqual(delivery.intent, "fulfillment")
        self.assertIn("não fazemos entrega", delivery.fallback)

        pickup = answer_from_store(self.tenant, "posso retirar?")
        self.assertEqual(pickup.intent, "fulfillment")
        self.assertIn("Pode retirar sim", pickup.fallback)
        self.assertIn("Rua das Flores", pickup.fallback)

    def test_delivery_areas_list_requires_city_when_multiple_cities(self):
        DeliveryZone.objects.create(
            tenant=self.tenant, city="Cotia", neighborhood="Centro",
            fee=Decimal("12.00"), is_active=True,
        )
        answer = answer_from_store(self.tenant, "quais bairros vcs entregam?")
        self.assertEqual(answer.intent, "delivery_areas")
        self.assertIn("Itapevi", answer.fallback)
        self.assertIn("Cotia", answer.fallback)
        self.assertIn("Qual cidade", answer.fallback)

        city_answer = answer_from_store(self.tenant, "quais bairros vcs entregam em Itapevi?")
        self.assertEqual(city_answer.intent, "delivery_areas")
        self.assertIn("Jardim Paulista", city_answer.fallback)
        self.assertIn("R$ 7,00", city_answer.fallback)
        self.assertNotIn("Cotia", city_answer.fallback)

    def test_product_description_uses_registered_description(self):
        self.product.description = "Refrigerante Coca-Cola garrafa 2 litros, servido gelado."
        self.product.save(update_fields=["description"])
        answer = answer_from_store(self.tenant, "o que vem na coca cola 2l?")
        self.assertEqual(answer.intent, "product_description")
        self.assertIn("garrafa 2 litros", answer.fallback)
        self.assertIn(product_url(self.tenant, self.product), answer.fallback)

    def test_product_customizations_list_real_options_and_prices(self):
        label = CustomizationGroupLabel.objects.create(
            tenant=self.tenant, name="Adicionais"
        )
        group = CustomizationGroup.objects.create(
            tenant=self.tenant, category=self.category, label=label,
            min_options=0, max_options=2, is_active=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant, group=group, name="Gelo extra",
            price=Decimal("1.50"), is_available=True,
        )
        answer = answer_from_store(self.tenant, "quais adicionais tem na coca cola 2l?")
        self.assertEqual(answer.intent, "customization")
        self.assertIn("Gelo extra", answer.fallback)
        self.assertIn("R$ 1,50", answer.fallback)
        self.assertIn(product_url(self.tenant, self.product), answer.fallback)

    def test_specific_customization_option_can_be_found_without_product_name(self):
        label = CustomizationGroupLabel.objects.create(
            tenant=self.tenant, name="Adicionais"
        )
        group = CustomizationGroup.objects.create(
            tenant=self.tenant, category=self.category, label=label,
            min_options=0, max_options=2, is_active=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant, group=group, name="Limão extra",
            price=Decimal("2.00"), is_available=True,
        )
        answer = answer_from_store(self.tenant, "quanto custa adicionar limao extra?")
        self.assertEqual(answer.intent, "customization")
        self.assertIn("Limão extra", answer.fallback)
        self.assertIn("R$ 2,00", answer.fallback)

    def test_promotions_include_discounted_products_and_only_public_active_coupons(self):
        from apps.coupons.models import AudienceType, CouponCampaign, DiscountType

        self.product.sale_price = Decimal("11.90")
        self.product.save(update_fields=["sale_price"])
        CouponCampaign.objects.create(
            tenant=self.tenant,
            name="Oferta pública",
            code="VEM10",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            minimum_order_value=Decimal("20.00"),
            audience_type=AudienceType.ALL,
            is_active=True,
        )
        CouponCampaign.objects.create(
            tenant=self.tenant,
            name="Privado",
            code="SEGREDO",
            discount_type=DiscountType.FIXED_AMOUNT,
            discount_value=Decimal("5.00"),
            audience_type=AudienceType.SPECIFIC,
            is_active=True,
        )
        answer = answer_from_store(self.tenant, "tem promocao ou cupom?")
        self.assertEqual(answer.intent, "promotion")
        self.assertIn("Coca-Cola 2L", answer.fallback)
        self.assertIn("R$ 14,90", answer.fallback)
        self.assertIn("R$ 11,90", answer.fallback)
        self.assertIn("VEM10", answer.fallback)
        self.assertNotIn("SEGREDO", answer.fallback)

    def test_product_characteristics_use_only_registered_fields(self):
        self.product.is_vegan = True
        self.product.is_spicy = True
        self.product.allergens = "glúten, leite"
        self.product.calories = 180
        self.product.prep_time = 5
        self.product.weight = Decimal("200.00")
        self.product.save()

        vegan = answer_from_store(self.tenant, "a coca cola 2l e vegana?")
        self.assertEqual(vegan.intent, "product_details")
        self.assertIn("vegano", vegan.fallback.lower())

        spicy = answer_from_store(self.tenant, "a coca cola 2l e picante?")
        self.assertIn("picante", spicy.fallback.lower())

        calories = answer_from_store(self.tenant, "quantas calorias tem a coca cola 2l?")
        self.assertIn("180 kcal", calories.fallback)

        prep = answer_from_store(self.tenant, "qual o tempo de preparo da coca cola 2l?")
        self.assertIn("5 min", prep.fallback)
        self.assertIn("não inclui o tempo total de entrega", prep.fallback)

        weight = answer_from_store(self.tenant, "qual o peso da coca cola 2l?")
        self.assertIn("200 g", weight.fallback)

    def test_allergen_answer_never_infers_safety_from_blank_field(self):
        self.product.allergens = ""
        self.product.save(update_fields=["allergens"])
        answer = answer_from_store(self.tenant, "a coca cola 2l tem gluten?")
        self.assertEqual(answer.intent, "product_allergens")
        self.assertIn("não cadastrou informações de alérgenos", answer.fallback)
        self.assertIn("contaminação cruzada", answer.fallback)
        self.assertNotIn("não contém", answer.fallback.lower())

    def test_generic_vegan_question_lists_only_available_vegan_products(self):
        self.product.is_vegan = True
        self.product.save(update_fields=["is_vegan"])
        other = Product.objects.create(
            tenant=self.tenant, category=self.category, name="Guaraná",
            price=Decimal("8.00"), is_available=True, is_vegan=False,
        )
        answer = answer_from_store(self.tenant, "tem opcao vegana?")
        self.assertEqual(answer.intent, "product_details")
        self.assertIn("Coca-Cola 2L", answer.fallback)
        self.assertNotIn(other.name, answer.fallback)

    def test_known_unavailable_product_is_reported_as_unavailable(self):
        self.product.stock = Decimal("0")
        self.product.save(update_fields=["stock"])
        answer = answer_from_store(self.tenant, "tem coca cola 2l?")
        self.assertEqual(answer.intent, "product_unavailable")
        self.assertIn("não está disponível no momento", answer.fallback)
        self.assertIn("Coca-Cola 2L", answer.fallback)

    @patch("apps.integrations.tasks.process_tenant_whatsapp_message.delay")
    def test_audio_webhook_is_queued_as_audio_without_transcription(self, delay):
        agent = get_or_create_agent(self.tenant)
        agent.instance_created = True
        agent.ai_enabled = True
        agent.save()
        payload = {
            "event": "MESSAGES_UPSERT",
            "instance": agent.instance_name,
            "data": {
                "key": {
                    "remoteJid": "5511988887777@s.whatsapp.net",
                    "fromMe": False,
                    "id": "AUDIO-1",
                },
                "message": {"audioMessage": {"seconds": 4, "ptt": True}},
            },
        }
        response = self.client.post(
            "/integracoes/evolution/tenant-webhook/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_VDD_WEBHOOK_TOKEN="t" * 48,
        )
        self.assertEqual(response.status_code, 202)
        delay.assert_called_once_with(
            agent.pk, "AUDIO-1", "5511988887777", "", "audio"
        )

    @patch("apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text")
    def test_audio_gets_text_only_guidance(self, send_text):
        send_text.return_value = "OUT-AUDIO"
        agent = get_or_create_agent(self.tenant)
        agent.ai_enabled = True
        agent.instance_created = True
        agent.status = TenantWhatsAppAgent.Status.OPEN
        agent.save()
        result = process_tenant_whatsapp_message(
            agent.pk, "IN-AUDIO", "5511988887777", "", "audio"
        )
        self.assertEqual(result, "answered:audio")
        reply = send_text.call_args.args[2]
        self.assertIn("não consigo interpretar mensagens de áudio", reply)
        self.assertIn("texto", reply.lower())
