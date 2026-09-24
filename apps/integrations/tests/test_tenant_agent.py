import json
from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.integrations.models import (
    TenantWhatsAppAgent,
    TenantWhatsAppConversation,
    TenantWhatsAppGroupNotice,
)
from apps.integrations.tasks import (
    notify_tenant_whatsapp_group_once,
    process_tenant_whatsapp_message,
)
from apps.integrations.whatsapp_agent.connection import (
    apply_connection_webhook,
    connect_agent,
    disconnect_agent,
    get_or_create_agent,
    monitor_agent,
)
from apps.integrations.whatsapp_agent.agent import answer as agent_answer
from apps.integrations.whatsapp_agent.knowledge import answer_from_store, normalize, product_url
from apps.integrations.whatsapp_agent.provider import extract_group_message, extract_message
from apps.integrations.whatsapp.client import EvolutionError
from apps.orders.models import Order
from apps.orders.services import build_whatsapp_message
from apps.orders.whatsapp_marker import extract_order_id
from apps.stores.models import (
    Category,
    CustomizationGroup,
    CustomizationGroupLabel,
    CustomizationOption,
    HalfProduct,
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

    def test_disconnect_accepts_provider_error_when_state_is_already_close(self):
        agent = get_or_create_agent(self.tenant)
        agent.instance_created = True
        agent.status = TenantWhatsAppAgent.Status.OPEN
        agent.save()
        client = Mock()
        client.logout.side_effect = EvolutionError("unavailable")
        client.status.return_value = "close"

        disconnect_agent(agent, client=client)

        agent.refresh_from_db()
        self.assertEqual(agent.status, TenantWhatsAppAgent.Status.PAIRING)
        self.assertTrue(agent.requires_pairing)
        self.assertIsNone(agent.next_reconnect_at)
        client.logout.assert_called_once_with(agent.instance_name)
        client.status.assert_called_once_with(agent.instance_name)

    def test_disconnect_keeps_provider_error_when_instance_remains_open(self):
        agent = get_or_create_agent(self.tenant)
        agent.instance_created = True
        agent.status = TenantWhatsAppAgent.Status.OPEN
        agent.save()
        client = Mock()
        client.logout.side_effect = EvolutionError("unavailable")
        client.status.return_value = "open"

        with self.assertRaises(EvolutionError):
            disconnect_agent(agent, client=client)

    def test_connect_applies_group_delivery_settings_to_existing_instance(self):
        agent = get_or_create_agent(self.tenant)
        agent.instance_created = True
        agent.status = TenantWhatsAppAgent.Status.OPEN
        agent.save()
        client = Mock()
        client.status.return_value = "open"

        qr = connect_agent(agent, client=client)

        self.assertIsNone(qr)
        client.set_agent_settings.assert_called_once_with(agent.instance_name)

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

    @patch("apps.integrations.tasks.notify_tenant_whatsapp_group_once.delay")
    def test_group_message_queues_private_notice(self, delay):
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
        self.assertEqual(response.status_code, 202)
        delay.assert_called_once_with(agent.pk, "123456@g.us")

    @patch("apps.integrations.tasks.notify_tenant_whatsapp_group_once.delay")
    def test_group_with_persisted_notice_stays_silent(self, delay):
        agent = get_or_create_agent(self.tenant)
        agent.instance_created = True
        agent.ai_enabled = True
        agent.save()
        TenantWhatsAppGroupNotice.objects.create(
            tenant=self.tenant, group_jid="123456@g.us", sent_at=timezone.now()
        )
        payload = {
            "event": "MESSAGES_UPSERT",
            "instance": agent.instance_name,
            "data": {
                "key": {
                    "remoteJid": "123456@g.us",
                    "fromMe": False,
                    "id": "GROUP-2",
                },
                "message": {"conversation": "Outra mensagem"},
            },
        }
        response = self.client.post(
            "/integracoes/evolution/tenant-webhook/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_VDD_WEBHOOK_TOKEN="t" * 48,
        )
        self.assertEqual(response.status_code, 202)
        delay.assert_not_called()

    @patch("apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text")
    def test_group_notice_is_persisted_and_sent_only_once(self, send_text):
        send_text.return_value = "GROUP-OUT-1"
        agent = get_or_create_agent(self.tenant)
        agent.instance_created = True
        agent.ai_enabled = True
        agent.status = TenantWhatsAppAgent.Status.OPEN
        agent.save()

        first = notify_tenant_whatsapp_group_once(agent.pk, "123456@g.us")
        second = notify_tenant_whatsapp_group_once(agent.pk, "123456@g.us")

        self.assertEqual(first, "notified")
        self.assertEqual(second, "already-notified")
        send_text.assert_called_once()
        args = send_text.call_args.args
        self.assertEqual(args[0], agent.instance_name)
        self.assertEqual(args[1], "123456@g.us")
        self.assertIn("apenas em conversa privada", args[2])
        self.assertIn("Me chama no privado que eu te ajudo por lá.", args[2])
        self.assertNotIn("diretamente por aqui", args[2])
        notice = TenantWhatsAppGroupNotice.objects.get(
            tenant=self.tenant, group_jid="123456@g.us"
        )
        self.assertIsNotNone(notice.sent_at)

    def test_group_extractor_keeps_group_jid_without_turning_it_into_phone(self):
        message = extract_group_message({
            "key": {
                "remoteJid": "123456@g.us",
                "fromMe": False,
                "id": "GROUP-EXTRACT-1",
            },
            "message": {"conversation": "Quanto custa?"},
        })
        self.assertEqual(message["group_jid"], "123456@g.us")
        self.assertFalse(message["from_me"])
        self.assertIsNone(extract_message({
            "key": {
                "remoteJid": "123456@g.us",
                "fromMe": False,
                "id": "GROUP-EXTRACT-1",
            },
            "message": {"conversation": "Quanto custa?"},
        }))


    def test_lid_without_alternate_jid_is_ignored(self):
        message = extract_message({
            "key": {
                "remoteJid": "999999999999999@lid",
                "fromMe": False,
                "id": "LID-1",
            },
            "message": {"conversation": "Oi"},
        })
        self.assertIsNone(message)

    def test_lid_with_routable_alternate_jid_uses_phone_number(self):
        message = extract_message({
            "key": {
                "remoteJid": "999999999999999@lid",
                "remoteJidAlt": "5511988887777@s.whatsapp.net",
                "fromMe": False,
                "id": "LID-2",
            },
            "message": {"conversation": "Oi"},
        })
        self.assertEqual(message["phone"], "5511988887777")
        self.assertEqual(message["text"], "Oi")

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

    def test_specific_customization_option_overlapping_product_name_works_without_product(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant, category=burgers, name="Combo Bacon",
            price=Decimal("39.90"), is_available=True,
        )
        label = CustomizationGroupLabel.objects.create(
            tenant=self.tenant, name="Adicionais"
        )
        group = CustomizationGroup.objects.create(
            tenant=self.tenant, category=burgers, label=label,
            min_options=0, max_options=3, is_active=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant, group=group, name="Bacon extra QA",
            price=Decimal("6.00"), is_available=True,
        )
        answer = answer_from_store(
            self.tenant, "quanto custa adicionar bacon extra QA?"
        )
        self.assertEqual(answer.intent, "customization")
        self.assertIn("Bacon extra QA", answer.fallback)
        self.assertIn("R$ 6,00", answer.fallback)
        self.assertNotIn("Combo Bacon", answer.fallback)

    def test_unknown_global_customization_does_not_match_only_generic_extra_word(self):
        label = CustomizationGroupLabel.objects.create(
            tenant=self.tenant, name="Adicionais"
        )
        group = CustomizationGroup.objects.create(
            tenant=self.tenant, category=self.category, label=label,
            min_options=0, max_options=3, is_active=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant, group=group, name="Bacon extra",
            price=Decimal("6.00"), is_available=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant, group=group, name="Cheddar extra",
            price=Decimal("4.50"), is_available=True,
        )
        answer = answer_from_store(
            self.tenant, "quanto custa adicionar cebola roxa extra?"
        )
        self.assertEqual(answer.intent, "customization")
        self.assertIn("não encontrei esse adicional", answer.fallback.lower())
        self.assertNotIn("Bacon extra", answer.fallback)
        self.assertNotIn("Cheddar extra", answer.fallback)

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
        self.assertIn("esgotado no momento", answer.fallback)
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

    def test_specific_customization_price_returns_only_requested_option(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        bacon = Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Bacon",
            price=Decimal("31.90"), is_available=True,
        )
        label = CustomizationGroupLabel.objects.create(
            tenant=self.tenant, name="Adicionais"
        )
        group = CustomizationGroup.objects.create(
            tenant=self.tenant, category=burgers, label=label,
            min_options=0, max_options=3, is_active=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant, group=group, name="Bacon extra",
            price=Decimal("6.00"), is_available=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant, group=group, name="Cheddar extra",
            price=Decimal("4.50"), is_available=True,
        )
        answer = answer_from_store(
            self.tenant, "quanto custa adicionar bacon extra no hambúrguer bacon?"
        )
        self.assertEqual(answer.intent, "customization")
        self.assertIn("Bacon extra", answer.fallback)
        self.assertIn("R$ 6,00", answer.fallback)
        self.assertNotIn("Cheddar extra", answer.fallback)
        self.assertIn(product_url(self.tenant, bacon), answer.fallback)

    def test_unknown_specific_customization_does_not_list_every_option(self):
        label = CustomizationGroupLabel.objects.create(
            tenant=self.tenant, name="Adicionais"
        )
        group = CustomizationGroup.objects.create(
            tenant=self.tenant, category=self.category, label=label,
            min_options=0, max_options=3, is_active=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant, group=group, name="Limão extra",
            price=Decimal("2.00"), is_available=True,
        )
        answer = answer_from_store(
            self.tenant, "quanto custa adicionar morango na coca cola 2l?"
        )
        self.assertEqual(answer.intent, "customization")
        self.assertIn("não encontrei esse adicional", answer.fallback.lower())
        self.assertNotIn("Limão extra", answer.fallback)

    def test_specific_unavailable_product_wins_over_generic_available_results(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Promo QA",
            price=Decimal("24.90"), is_available=True,
        )
        Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Vegano QA",
            price=Decimal("29.90"), is_available=True,
        )
        unavailable = Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Esgotado QA",
            price=Decimal("25.00"), is_available=False,
        )
        answer = answer_from_store(self.tenant, "tem hambúrguer esgotado QA?")
        self.assertEqual(answer.intent, "product_unavailable")
        self.assertIn(unavailable.name, answer.fallback)
        self.assertNotIn("Hambúrguer Promo QA", answer.fallback)

    def test_unknown_product_gets_natural_not_found_answer(self):
        answer = answer_from_store(self.tenant, "tem sushi de salmão?")
        self.assertEqual(answer.intent, "product_not_found")
        self.assertIn("sushi de salmão", answer.fallback.lower())
        self.assertIn("não encontrei", answer.fallback.lower())
        self.assertIn("cardápio", answer.fallback.lower())

    def test_catalog_and_order_start_go_directly_to_catalog(self):
        for question in ("me manda o cardápio", "quero fazer um pedido", "como pedir?"):
            answer = answer_from_store(self.tenant, question)
            self.assertEqual(answer.intent, "catalog")
            self.assertIn("bella-massa.lvh.me", answer.fallback)

    def test_order_status_hands_off_to_store_and_pauses_agent(self):
        answer = answer_from_store(self.tenant, "onde está meu pedido?")
        self.assertEqual(answer.intent, "order_status")
        self.assertEqual(answer.pause_minutes, 60)
        self.assertEqual(answer.pause_reason, "human")
        self.assertIn("equipe da loja", answer.fallback)

    def test_delivery_eta_never_invents_total_time(self):
        answer = answer_from_store(self.tenant, "quanto tempo demora a entrega?")
        self.assertEqual(answer.intent, "delivery_eta")
        self.assertIn("não tenho um prazo total", answer.fallback.lower())
        self.assertNotIn("minutos", answer.fallback.lower())

    def test_open_now_question_is_direct(self):
        BusinessHour.objects.create(
            tenant=self.tenant,
            weekday=timezone.localdate().weekday(),
            is_closed=False,
            opening_time=time(0, 0),
            closing_time=time(23, 59),
        )
        answer = answer_from_store(self.tenant, "vcs estão abertos?")
        self.assertEqual(answer.intent, "hours")
        self.assertIn("aberta agora", answer.fallback.lower())

    def test_payment_online_question_respects_real_availability(self):
        answer = answer_from_store(self.tenant, "posso pagar pix online pelo site?")
        self.assertEqual(answer.intent, "payment")
        self.assertIn("pagamento online não está habilitado", answer.fallback.lower())

    def test_unsupported_payment_method_is_not_claimed_as_accepted(self):
        answer = answer_from_store(self.tenant, "aceita cartão alimentação?")
        self.assertEqual(answer.intent, "payment")
        self.assertIn("não aparece entre as opções", answer.fallback.lower())
        self.assertNotIn("aceitamos sim", answer.fallback.lower())

    def test_specific_product_promotion_is_answered_without_listing_every_offer(self):
        self.product.sale_price = Decimal("11.90")
        self.product.save(update_fields=["sale_price"])
        answer = answer_from_store(self.tenant, "a coca cola 2l está em promoção?")
        self.assertEqual(answer.intent, "promotion")
        self.assertIn("Coca-Cola 2L", answer.fallback)
        self.assertIn("R$ 11,90", answer.fallback)
        self.assertNotIn("Cupons públicos", answer.fallback)

    def test_product_comparison_uses_real_prices_inside_category(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        cheap = Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Econômico",
            price=Decimal("19.90"), is_available=True,
        )
        Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Premium",
            price=Decimal("39.90"), is_available=True,
        )
        answer = answer_from_store(self.tenant, "qual hambúrguer é mais barato?")
        self.assertEqual(answer.intent, "product")
        self.assertIn(cheap.name, answer.fallback)
        self.assertIn("R$ 19,90", answer.fallback)

    def test_courtesy_message_does_not_dump_agent_menu(self):
        answer = answer_from_store(self.tenant, "obrigado")
        self.assertEqual(answer.intent, "thanks")
        self.assertIn("Por nada", answer.fallback)
        self.assertNotIn("cardápio, entrega", answer.fallback.lower())

    def test_ephemeral_media_is_unwrapped_and_classified(self):
        message = extract_message({
            "key": {
                "remoteJid": "5511988887777@s.whatsapp.net",
                "fromMe": False,
                "id": "IMG-WRAPPED-1",
            },
            "message": {
                "ephemeralMessage": {
                    "message": {
                        "imageMessage": {"caption": "essa foto"}
                    }
                }
            },
        })
        self.assertIsNotNone(message)
        self.assertEqual(message["kind"], "image")
        self.assertEqual(message["text"], "essa foto")

    @patch("apps.integrations.tasks.process_tenant_whatsapp_message.delay")
    def test_image_without_caption_is_queued_for_guidance(self, delay):
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
                    "id": "IMAGE-1",
                },
                "message": {"imageMessage": {"mimetype": "image/jpeg"}},
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
            agent.pk, "IMAGE-1", "5511988887777", "", "image"
        )

    @patch("apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text")
    def test_location_gets_city_and_neighborhood_guidance(self, send_text):
        send_text.return_value = "OUT-LOCATION"
        agent = get_or_create_agent(self.tenant)
        agent.ai_enabled = True
        agent.instance_created = True
        agent.status = TenantWhatsAppAgent.Status.OPEN
        agent.save()
        result = process_tenant_whatsapp_message(
            agent.pk, "IN-LOCATION", "5511988887777", "", "location"
        )
        self.assertEqual(result, "answered:location")
        reply = send_text.call_args.args[2]
        self.assertIn("cidade", reply.lower())
        self.assertIn("bairro", reply.lower())

    @override_settings(WHATSAPP_AGENT_OLLAMA_ENABLED=True)
    @patch("apps.integrations.whatsapp_agent.agent.naturalize")
    def test_naturalizer_cannot_invent_price_or_link(self, naturalize):
        naturalize.return_value = "Só R$ 0,01! https://evil.example/produto"
        reply = agent_answer(self.tenant, "quanto custa coca cola 2l?")
        self.assertIn("R$ 14,90", reply.text)
        self.assertNotIn("R$ 0,01", reply.text)
        self.assertNotIn("evil.example", reply.text)

    def test_comparison_followup_uses_products_from_previous_context(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        cheap = Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Econômico",
            price=Decimal("19.90"), is_available=True,
        )
        Product.objects.create(
            tenant=self.tenant, category=burgers, name="Hambúrguer Premium",
            price=Decimal("39.90"), is_available=True,
        )
        first = answer_from_store(self.tenant, "quais hambúrgueres vcs têm?")
        second = answer_from_store(self.tenant, "qual é o mais barato?", context=first.context)
        self.assertEqual(second.intent, "product")
        self.assertIn(cheap.name, second.fallback)

    def test_ordinal_followup_uses_previous_product_order(self):
        Product.objects.create(
            tenant=self.tenant, category=self.category, name="Guaraná 350 ml",
            price=Decimal("7.50"), is_available=True,
        )
        first = answer_from_store(self.tenant, "quais bebidas vcs têm?")
        products = first.context.get("product_ids")
        self.assertGreaterEqual(len(products), 2)
        expected = Product.objects.get(pk=products[1])
        second = answer_from_store(self.tenant, "quanto custa o segundo?", context=first.context)
        self.assertEqual(second.intent, "product")
        self.assertIn(expected.name, second.fallback)

    def test_half_half_uses_existing_commercial_rule_and_active_products(self):
        pizzas = Category.objects.create(tenant=self.tenant, name="Pizzas")
        calabresa = Product.objects.create(
            tenant=self.tenant, category=pizzas, name="Pizza Calabresa",
            price=Decimal("39.90"), is_available=True,
        )
        portuguesa = Product.objects.create(
            tenant=self.tenant, category=pizzas, name="Pizza Portuguesa",
            price=Decimal("44.90"), is_available=True,
        )
        # Product já cria HalfProduct automaticamente por signal. O teste deve
        # apenas garantir que as variantes existentes estejam ativas, sem tentar
        # violar o OneToOne de HalfProduct.product.
        HalfProduct.objects.update_or_create(
            product=calabresa,
            defaults={"tenant": self.tenant, "is_active": True},
        )
        HalfProduct.objects.update_or_create(
            product=portuguesa,
            defaults={"tenant": self.tenant, "is_active": True},
        )
        answer = answer_from_store(self.tenant, "faz pizza meio a meio?")
        self.assertEqual(answer.intent, "half_half")
        self.assertIn("Pizza Calabresa", answer.fallback)
        self.assertIn("Pizza Portuguesa", answer.fallback)
        self.assertIn("opção mais cara", answer.fallback)
        self.assertNotIn(self.product.name, answer.fallback)

    def test_half_half_question_with_funciona_does_not_become_hours(self):
        pizzas = Category.objects.create(tenant=self.tenant, name="Pizzas Artesanais")
        calabresa = Product.objects.create(
            tenant=self.tenant, category=pizzas, name="Pizza Calabresa Especial",
            price=Decimal("42.00"), is_available=True,
        )
        HalfProduct.objects.update_or_create(
            product=calabresa,
            defaults={"tenant": self.tenant, "is_active": True},
        )
        answer = answer_from_store(self.tenant, "como funciona a pizza meio a meio?")
        self.assertEqual(answer.intent, "half_half")
        self.assertIn("opção mais cara", answer.fallback)
        self.assertIn("Pizza Calabresa Especial", answer.fallback)


    def test_informal_description_variants_are_understood(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        bacon = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão brioche, carne e bacon.",
            price=Decimal("31.90"),
            is_available=True,
        )
        for question in (
            "oque vem no hamburguer bacon?",
            "q vem no hamb bacon?",
            "leva oq o hamb bacon?",
        ):
            answer = answer_from_store(self.tenant, question)
            self.assertEqual(answer.intent, "product_description", question)
            self.assertIn(bacon.description, answer.fallback, question)

    def test_faz_delivery_is_fulfillment_question(self):
        answer = answer_from_store(self.tenant, "faz delivery?")
        self.assertEqual(answer.intent, "fulfillment")
        self.assertIn("entrega", answer.fallback.lower())

    def test_cash_payment_is_not_confused_with_bathroom_business_info(self):
        for question in (
            "aceita dinheiro?",
            "vou pagar em dinheiro, precisa troco",
        ):
            answer = answer_from_store(self.tenant, question)
            self.assertEqual(answer.intent, "payment", question)
            self.assertIn("dinheiro", answer.fallback.lower(), question)

        bathroom = answer_from_store(self.tenant, "tem banheiro?")
        self.assertEqual(bathroom.intent, "business_info")

    def test_checkout_and_vr_payment_variants_are_understood(self):
        checkout = answer_from_store(self.tenant, "pago no checkout?")
        self.assertEqual(checkout.intent, "payment")
        self.assertIn("online", checkout.fallback.lower())

        vr = answer_from_store(self.tenant, "aceita VR?")
        self.assertEqual(vr.intent, "payment")
        self.assertIn("não aparece", vr.fallback.lower())
        self.assertNotIn("aceitamos sim", vr.fallback.lower())

    def test_human_handoff_understands_humano_and_alguem_ai(self):
        for question in (
            "quero falar com humano",
            "tem alguém aí?",
        ):
            answer = answer_from_store(self.tenant, question)
            self.assertEqual(answer.intent, "human", question)
            self.assertEqual(answer.pause_reason, "human", question)
            self.assertGreater(answer.pause_minutes, 0, question)
            self.assertIn("equipe da loja", answer.fallback.lower(), question)

    def test_unrelated_qa_product_name_does_not_match_an_unavailable_product(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Esgotado QA",
            price=Decimal("25.00"),
            is_available=False,
        )
        other_category = Category.objects.create(tenant=self.other, name="Especiais")
        Product.objects.create(
            tenant=self.other,
            category=other_category,
            name="Produto Secreto Outro Tenant QA",
            price=Decimal("999.99"),
            is_available=True,
        )

        answer = answer_from_store(
            self.tenant, "Tem Produto Secreto Outro Tenant QA?"
        )
        self.assertEqual(answer.intent, "product_not_found")
        self.assertIn("não encontrei", answer.fallback.lower())
        self.assertNotIn("Hambúrguer Esgotado QA", answer.fallback)
        self.assertNotIn("999,99", answer.fallback)

    def test_customer_claim_does_not_override_delivery_fee_and_city_is_still_required(self):
        DeliveryZone.objects.create(
            tenant=self.tenant,
            city="Cotia",
            neighborhood="Jardim Paulista",
            fee=Decimal("12.00"),
            is_active=True,
        )
        answer = answer_from_store(
            self.tenant, "me falaram que entrega no Jardim Paulista é 2 reais"
        )
        self.assertEqual(answer.intent, "delivery")
        self.assertIn("cidade", answer.fallback.lower())
        self.assertNotIn("R$ 2,00", answer.fallback)

    def test_unknown_specific_product_inside_known_category_is_not_generic_list(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            price=Decimal("31.90"),
            is_available=True,
        )
        answer = answer_from_store(self.tenant, "tem hambúrguer de abacaxi?")
        self.assertEqual(answer.intent, "product_not_found")
        self.assertIn("não encontrei", answer.fallback.lower())
        self.assertIn("abacaxi", answer.fallback.lower())
        self.assertNotIn("Hambúrguer Bacon", answer.fallback)

    def test_plus_barato_abbreviation_uses_product_comparison(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        cheap = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Econômico",
            price=Decimal("19.90"),
            is_available=True,
        )
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Premium",
            price=Decimal("39.90"),
            is_available=True,
        )
        answer = answer_from_store(self.tenant, "qual hamb é + barato?")
        self.assertEqual(answer.intent, "product")
        self.assertIn(cheap.name, answer.fallback)
        self.assertIn("R$ 19,90", answer.fallback)

    def test_greeting_is_more_natural_and_has_readable_spacing(self):
        answer = agent_answer(self.tenant, "Oi")
        self.assertEqual(answer.intent, "greeting")
        self.assertIn("Tudo bem?", answer.text)
        self.assertIn("Como posso te ajudar?", answer.text)
        self.assertNotIn("Sou o assistente", answer.text)
        self.assertIn("\n\n", answer.text)
        self.assertNotIn("\n\n\n", answer.text)

    def test_human_handoff_uses_continuity_wording(self):
        answer = answer_from_store(self.tenant, "quero falar com uma pessoa")
        self.assertEqual(answer.intent, "human")
        self.assertIn("equipe da loja continuar seu atendimento", answer.fallback)
        self.assertGreater(answer.pause_minutes, 0)

    def test_greeting_ola_variants_do_not_match_cola_products(self):
        for question in ("Olá", "Olaaa"):
            answer = answer_from_store(self.tenant, question)
            self.assertEqual(answer.intent, "greeting", question)
            self.assertNotIn("Coca-Cola", answer.fallback, question)

    def test_q_hamb_abbreviation_lists_hamburgers(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            price=Decimal("31.90"),
            is_available=True,
        )
        answer = answer_from_store(self.tenant, "q hamb vcs tem?")
        self.assertEqual(answer.intent, "product")
        self.assertIn("Hambúrguer Bacon", answer.fallback)

    def test_customization_option_name_wins_over_similar_product_name(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        combos = Category.objects.create(tenant=self.tenant, name="Combos")
        Product.objects.create(
            tenant=self.tenant,
            category=combos,
            name="Combo Bacon",
            price=Decimal("39.90"),
            is_available=True,
        )
        label = CustomizationGroupLabel.objects.create(
            tenant=self.tenant,
            name="Adicionais",
        )
        group = CustomizationGroup.objects.create(
            tenant=self.tenant,
            category=burgers,
            label=label,
            min_options=0,
            max_options=5,
            is_active=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant,
            group=group,
            name="Bacon extra QA",
            price=Decimal("6.00"),
            is_available=True,
        )

        for question in (
            "quanto é o extra de bacon QA?",
            "Tem bacon extra QA?",
        ):
            answer = answer_from_store(self.tenant, question)
            self.assertEqual(answer.intent, "customization", question)
            self.assertIn("Bacon extra QA", answer.fallback, question)
            self.assertIn("R$ 6,00", answer.fallback, question)
            self.assertNotIn("Combo Bacon", answer.fallback, question)

    def test_unknown_named_extra_without_product_returns_not_found(self):
        for question in (
            "tem cebola roxa extra?",
            "tem molho trufado extra?",
        ):
            answer = answer_from_store(self.tenant, question)
            self.assertEqual(answer.intent, "customization", question)
            self.assertIn("não encontrei", answer.fallback.lower(), question)

    def test_explicit_product_price_overrides_delivery_context(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            price=Decimal("31.90"),
            is_available=True,
        )
        context = {
            "intent": "delivery_fee",
            "city": "Itapevi",
            "neighborhood": "Centro",
        }
        answer = answer_from_store(
            self.tenant,
            "qnt custa o hamb bacon?",
            context=context,
        )
        self.assertEqual(answer.intent, "product")
        self.assertIn("Hambúrguer Bacon", answer.fallback)
        self.assertIn("R$ 31,90", answer.fallback)

    def test_short_human_handoff_variants_are_understood(self):
        for question in ("quero humano", "tem atendente?"):
            answer = answer_from_store(self.tenant, question)
            self.assertEqual(answer.intent, "human", question)
            self.assertEqual(answer.pause_reason, "human", question)
            self.assertGreater(answer.pause_minutes, 0, question)

    def test_hamburger_english_spelling_maps_to_hamburguer_category(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            price=Decimal("31.90"),
            is_available=True,
        )
        answer = answer_from_store(self.tenant, "tem hamburger?")
        self.assertEqual(answer.intent, "product")
        self.assertIn("Hambúrguer Bacon", answer.fallback)

    def test_quais_complementos_is_list_request_not_specific_option(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        product = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            price=Decimal("31.90"),
            is_available=True,
        )
        label = CustomizationGroupLabel.objects.create(
            tenant=self.tenant,
            name="Adicionais",
        )
        group = CustomizationGroup.objects.create(
            tenant=self.tenant,
            category=burgers,
            label=label,
            min_options=0,
            max_options=5,
            is_active=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant,
            group=group,
            name="Bacon extra QA",
            price=Decimal("6.00"),
            is_available=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant,
            group=group,
            name="Cheddar extra QA",
            price=Decimal("4.50"),
            is_available=True,
        )

        answer = answer_from_store(
            self.tenant,
            "quais complementos do hamburguer bacon?",
        )
        self.assertEqual(answer.intent, "customization")
        self.assertIn(product.name, answer.fallback)
        self.assertIn("Bacon extra QA", answer.fallback)
        self.assertIn("Cheddar extra QA", answer.fallback)

    def test_more_natural_human_handoff_variants_are_understood(self):
        for question in (
            "chama um atendente",
            "quero uma pessoa",
        ):
            answer = answer_from_store(self.tenant, question)
            self.assertEqual(answer.intent, "human", question)
            self.assertEqual(answer.pause_reason, "human", question)
            self.assertGreater(answer.pause_minutes, 0, question)

    def test_hambuger_typo_maps_to_hamburguer_category(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            price=Decimal("31.90"),
            is_available=True,
        )

        answer = answer_from_store(self.tenant, "tem hambuger?")

        self.assertEqual(answer.intent, "product")
        self.assertIn("Hambúrguer Bacon", answer.fallback)

    def test_extra_substring_inside_unrelated_word_does_not_trigger_customization(self):
        pizzas = Category.objects.create(tenant=self.tenant, name="Pizzas")
        Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza Calabresa",
            price=Decimal("39.90"),
            is_available=True,
        )

        answer = answer_from_store(
            self.tenant,
            "tem pizza de jaca extraterrestre?",
        )

        self.assertEqual(answer.intent, "product_not_found")
        self.assertIn("não encontrei", answer.fallback.lower())

    def test_order_start_without_article_opens_catalog(self):
        for question in ("quero fazer pedido", "fazer pedido"):
            answer = answer_from_store(self.tenant, question)
            self.assertEqual(answer.intent, "catalog", question)
            self.assertIn("cardápio", answer.fallback.lower(), question)

    def test_natural_product_composition_questions_use_description(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        bacon = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão, carne, cheddar e bacon crocante.",
            price=Decimal("31.90"),
            is_available=True,
        )
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Combo Bacon",
            description="Combo com bebida.",
            price=Decimal("43.90"),
            is_available=True,
        )

        for question in (
            "o hamb bacon tem bacon?",
            "leva bacon no hamb bacon?",
            "tem cheddar no hamb bacon?",
        ):
            answer = answer_from_store(self.tenant, question)
            self.assertEqual(answer.intent, "product_description", question)
            self.assertIn(bacon.name, answer.fallback, question)
            self.assertIn("bacon crocante", answer.fallback, question)

    def test_contextual_ingredient_pronoun_keeps_previous_product(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        bacon = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão, carne, cheddar e bacon crocante.",
            price=Decimal("31.90"),
            is_available=True,
        )
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Combo Bacon",
            description="Combo com bebida.",
            price=Decimal("43.90"),
            is_available=True,
        )

        context = {"intent": "product", "product_ids": [bacon.pk]}
        answer = answer_from_store(
            self.tenant,
            "e tem bacon nele?",
            context=context,
        )
        self.assertEqual(answer.intent, "product_description")
        self.assertIn(bacon.name, answer.fallback)
        self.assertIn("bacon crocante", answer.fallback)
        self.assertNotIn("Combo Bacon", answer.fallback)

    def test_plain_product_availability_does_not_become_composition(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão, carne e bacon.",
            price=Decimal("31.90"),
            is_available=True,
        )

        answer = answer_from_store(self.tenant, "tem hamburger bacon?")
        self.assertEqual(answer.intent, "product")
        self.assertIn("Hambúrguer Bacon", answer.fallback)

    def test_hamburgeres_plural_typo_maps_to_hamburguer_category(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            price=Decimal("31.90"),
            is_available=True,
        )

        answer = answer_from_store(self.tenant, "tem hamburgeres?")

        self.assertEqual(answer.intent, "product")
        self.assertIn("Hambúrguer Bacon", answer.fallback)

    def test_como_e_o_product_uses_description(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        product = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão brioche, carne, cheddar e bacon crocante.",
            price=Decimal("31.90"),
            is_available=True,
        )

        answer = answer_from_store(self.tenant, "como é o hamb bacon?")

        self.assertEqual(answer.intent, "product_description")
        self.assertIn(product.name, answer.fallback)
        self.assertIn("bacon crocante", answer.fallback)

    def test_fazem_delivery_is_fulfillment_capability_question(self):
        answer = answer_from_store(self.tenant, "fazem delivery?")

        self.assertEqual(answer.intent, "fulfillment")
        self.assertIn("entrega", answer.fallback.lower())

    def test_posso_pegar_na_loja_is_pickup_fulfillment_question(self):
        answer = answer_from_store(self.tenant, "posso pegar na loja?")

        self.assertEqual(answer.intent, "fulfillment")
        self.assertIn("retirar", answer.fallback.lower())


    def test_general_plural_matching_handles_portuguese_inflections(self):
        breads = Category.objects.create(tenant=self.tenant, name="Pães")
        Product.objects.create(
            tenant=self.tenant,
            category=breads,
            name="Artesanal da Casa",
            price=Decimal("12.90"),
            is_available=True,
        )

        answer = answer_from_store(self.tenant, "tem pao?")

        self.assertEqual(answer.intent, "product")
        self.assertIn("Artesanal da Casa", answer.fallback)

    def test_product_description_understands_common_whatsapp_phrases_and_typos(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        product = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão brioche, carne, cheddar, bacon crocante e molho especial.",
            price=Decimal("31.90"),
            is_available=True,
        )

        questions = (
            "oq vem no hamb bacon?",
            "q veim no lanxe bacon?",
            "o que leva o hamb bacon?",
            "vem com oq o hamb bacon?",
            "do q eh feito o hamb bacon?",
            "quais igredientes do hamb bacon?",
            "qual composisao do hamb bacon?",
            "me descreve o hamb bacon",
            "qual rexeio do hamb bacon?",
            "oq vai dentro do hamb bacon?",
            "o que tem no hamb bacon?",
            "o hamb bacon é feito de que?",
            "o hamb bacon vem com oq?",
        )

        for question in questions:
            with self.subTest(question=question):
                answer = answer_from_store(self.tenant, question)
                self.assertEqual(answer.intent, "product_description")
                self.assertIn(product.name, answer.fallback)
                self.assertIn("bacon crocante", answer.fallback)

    def test_product_description_context_understands_generic_lanche_followup(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        product = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão brioche, carne, cheddar e bacon crocante.",
            price=Decimal("31.90"),
            is_available=True,
        )

        context = {"intent": "product", "product_ids": [product.pk]}
        for question in (
            "e oq vem nele?",
            "e o que esse lanche leva?",
            "esse lanche vem com oq?",
        ):
            with self.subTest(question=question):
                answer = answer_from_store(self.tenant, question, context=context)
                self.assertEqual(answer.intent, "product_description")
                self.assertIn(product.name, answer.fallback)
                self.assertIn("bacon crocante", answer.fallback)

    def test_description_expansion_keeps_specific_intent_priorities(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        product = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão, carne, cheddar e bacon.",
            allergens="glúten, leite",
            price=Decimal("31.90"),
            is_available=True,
        )
        label = CustomizationGroupLabel.objects.create(
            tenant=self.tenant,
            name="Adicionais",
        )
        group = CustomizationGroup.objects.create(
            tenant=self.tenant,
            category=burgers,
            label=label,
            min_options=0,
            max_options=5,
            is_active=True,
        )
        CustomizationOption.objects.create(
            tenant=self.tenant,
            group=group,
            name="Bacon extra",
            price=Decimal("6.00"),
            is_available=True,
        )

        availability = answer_from_store(self.tenant, "tem hambúrguer bacon?")
        customization = answer_from_store(
            self.tenant, "quais adicionais tem no hambúrguer bacon?"
        )
        allergens = answer_from_store(
            self.tenant, "o hambúrguer bacon tem glutem?"
        )

        self.assertEqual(availability.intent, "product")
        self.assertEqual(customization.intent, "customization")
        self.assertEqual(allergens.intent, "product_allergens")
        self.assertIn(product.name, allergens.fallback)

    def test_product_listing_questions_do_not_become_description(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão, carne, queijo e bacon.",
            price=Decimal("31.90"),
            is_available=True,
        )

        for question in (
            "q hamb vcs tem?",
            "que hamb vcs tem?",
            "que lanches vcs tem?",
            "quais hamburgueres vcs tem?",
            "tem hamburgeres?",
        ):
            with self.subTest(question=question):
                answer = answer_from_store(self.tenant, question)
                self.assertEqual(answer.intent, "product")
                self.assertIn("Hambúrguer Bacon", answer.fallback)

    def test_explicit_product_composition_subject_still_uses_description(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        product = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão brioche, carne, cheddar e bacon crocante.",
            price=Decimal("31.90"),
            is_available=True,
        )

        for question in (
            "o que o hamb bacon tem?",
            "o que esse lanche leva?",
            "q vem no hamb bacon?",
            "que tem no hamb bacon?",
        ):
            with self.subTest(question=question):
                answer = answer_from_store(self.tenant, question)
                self.assertEqual(answer.intent, "product_description")
                self.assertIn(product.name, answer.fallback)
                self.assertIn("bacon crocante", answer.fallback)


    def test_ingredient_search_lists_all_products_matching_description(self):
        pizzas = Category.objects.create(tenant=self.tenant, name="Pizzas")
        frango = Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza Especial",
            description="Frango desfiado, catupiry, milho e mussarela.",
            price=Decimal("42.90"),
            is_available=True,
        )
        casa = Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza da Casa",
            description="Mussarela, frango, bacon e cheddar.",
            price=Decimal("46.90"),
            is_available=True,
        )
        calabresa = Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza Calabresa",
            description="Calabresa, cebola e mussarela.",
            price=Decimal("39.90"),
            is_available=True,
        )

        for question in (
            "tem pizza de frango?",
            "quais pizzas tem frango?",
            "q pizza tem frango?",
        ):
            with self.subTest(question=question):
                answer = answer_from_store(self.tenant, question)
                self.assertEqual(answer.intent, "product")
                self.assertIn(frango.name, answer.fallback)
                self.assertIn(casa.name, answer.fallback)
                self.assertNotIn(calabresa.name, answer.fallback)
                self.assertIn(product_url(self.tenant, frango), answer.fallback)
                self.assertIn(product_url(self.tenant, casa), answer.fallback)
                self.assertIn("Frango desfiado", answer.fallback)

    def test_missing_requested_category_does_not_fall_back_to_other_products(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        burger = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão, carne, queijo e bacon crocante.",
            price=Decimal("31.90"),
            is_available=True,
        )
        portions = Category.objects.create(tenant=self.tenant, name="Porções")
        portion = Product.objects.create(
            tenant=self.tenant,
            category=portions,
            name="Batata com Bacon",
            description="Batata frita, cheddar e bacon crocante.",
            price=Decimal("28.90"),
            is_available=True,
        )

        answer = answer_from_store(
            self.tenant,
            "tem pizza de frango e bacon?",
        )

        self.assertEqual(answer.intent, "product_not_found")
        self.assertIn("não encontrei", answer.fallback.lower())
        self.assertIn("pizzas", answer.fallback.lower())
        self.assertNotIn(burger.name, answer.fallback)
        self.assertNotIn(portion.name, answer.fallback)

    def test_ingredient_search_is_generic_for_any_registered_ingredient_and_typos(self):
        pizzas = Category.objects.create(tenant=self.tenant, name="Pizzas")
        product = Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza Cremosa",
            description="Frango desfiado, catupiry e cheddar cremoso.",
            price=Decimal("44.90"),
            is_available=True,
        )

        for question in (
            "tem pizza com catupiry?",
            "tem pizza com catupiri?",
            "tem pizza com cheddar?",
            "tem pizza com chedar?",
        ):
            with self.subTest(question=question):
                answer = answer_from_store(self.tenant, question)
                self.assertEqual(answer.intent, "product")
                self.assertIn(product.name, answer.fallback)
                self.assertIn(product_url(self.tenant, product), answer.fallback)

    def test_ingredient_search_without_category_searches_catalog_but_not_other_tenant(self):
        pizzas = Category.objects.create(tenant=self.tenant, name="Pizzas")
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        pizza = Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza Bacon",
            description="Mussarela, bacon crocante e cebola.",
            price=Decimal("43.90"),
            is_available=True,
        )
        burger = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Especial da Casa",
            description="Pão, carne, queijo e bacon crocante.",
            price=Decimal("32.90"),
            is_available=True,
        )
        other_category = Category.objects.create(tenant=self.other, name="Pizzas")
        Product.objects.create(
            tenant=self.other,
            category=other_category,
            name="Pizza Bacon Secreta",
            description="Muito bacon.",
            price=Decimal("1.00"),
            is_available=True,
        )

        answer = answer_from_store(self.tenant, "tem algo com bacon?")

        self.assertEqual(answer.intent, "product")
        self.assertIn(pizza.name, answer.fallback)
        self.assertIn(burger.name, answer.fallback)
        self.assertNotIn("Pizza Bacon Secreta", answer.fallback)

    def test_ingredient_search_with_multiple_terms_requires_all_terms(self):
        pizzas = Category.objects.create(tenant=self.tenant, name="Pizzas")
        complete = Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza Frango Cremosa",
            description="Frango desfiado, catupiry, milho e mussarela.",
            price=Decimal("45.90"),
            is_available=True,
        )
        only_frango = Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza Frango Simples",
            description="Frango desfiado, milho e mussarela.",
            price=Decimal("39.90"),
            is_available=True,
        )

        answer = answer_from_store(
            self.tenant,
            "tem pizza com frango e catupiry?",
        )

        self.assertEqual(answer.intent, "product")
        self.assertIn(complete.name, answer.fallback)
        self.assertNotIn(only_frango.name, answer.fallback)

    def test_ingredient_search_keeps_specific_product_and_shorthand_priorities(self):
        pizzas = Category.objects.create(tenant=self.tenant, name="Pizzas")
        portuguesa = Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza Portuguesa",
            description="Presunto, ovo, cebola, ervilha e mussarela.",
            price=Decimal("44.90"),
            is_available=True,
        )
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        bacon = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão, carne, queijo e bacon.",
            price=Decimal("31.90"),
            is_available=True,
        )

        specific = answer_from_store(
            self.tenant,
            "a Pizza Portuguesa tem frango?",
        )
        shorthand = answer_from_store(self.tenant, "tem hamb bacon?")

        self.assertEqual(specific.intent, "product_description")
        self.assertIn(portuguesa.name, specific.fallback)
        self.assertEqual(shorthand.intent, "product")
        self.assertIn(bacon.name, shorthand.fallback)

    def test_ingredient_typo_does_not_collide_with_hours_vocabulary(self):
        pizzas = Category.objects.create(tenant=self.tenant, name="Pizzas")
        product = Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza Calabresa",
            description="Calabresa, cebola, mussarela e orégano.",
            price=Decimal("39.90"),
            is_available=True,
        )

        answer = answer_from_store(self.tenant, "tem pizza com calabreza?")

        self.assertEqual(answer.intent, "product")
        self.assertIn(product.name, answer.fallback)
        self.assertNotIn("Estes são os horários", answer.fallback)

    def test_generic_ingredient_questions_do_not_trigger_human_handoff(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        bacon = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão, carne, queijo, bacon e cebola.",
            price=Decimal("31.90"),
            is_available=True,
        )
        frango = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Lanche de Frango",
            description="Pão, frango desfiado, queijo e milho.",
            price=Decimal("29.90"),
            is_available=True,
        )

        cases = (
            ("tem alguma coisa com bacon?", bacon.name),
            ("tem alguma coisa com frango?", frango.name),
            ("que produtos levam cebola?", bacon.name),
        )
        for question, expected_name in cases:
            with self.subTest(question=question):
                answer = answer_from_store(self.tenant, question)
                self.assertEqual(answer.intent, "product")
                self.assertIn(expected_name, answer.fallback)
                self.assertEqual(answer.pause_minutes, 0)

    def test_ingredient_search_does_not_fuzzy_match_generic_adjective(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        product = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Lanche Especial",
            description="Pão, carne, queijo e molho especial.",
            price=Decimal("30.00"),
            is_available=True,
        )

        answer = answer_from_store(
            self.tenant,
            "tem lanche com ingrediente espacial?",
        )

        self.assertEqual(answer.intent, "product_not_found")
        self.assertNotIn(product.name, answer.fallback)
        self.assertIn("não encontrei", answer.fallback.lower())

    def test_multi_ingredient_search_does_not_fall_back_to_partial_matches(self):
        pizzas = Category.objects.create(tenant=self.tenant, name="Pizzas")
        Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza Frango e Bacon",
            description="Frango desfiado, bacon, mussarela e cebola.",
            price=Decimal("45.90"),
            is_available=True,
        )

        for question in (
            "tem pizza com frango e plutonio?",
            "tem pizza com bacon e jaca radioativa?",
        ):
            with self.subTest(question=question):
                answer = answer_from_store(self.tenant, question)
                self.assertEqual(answer.intent, "product_not_found")
                self.assertIn("não encontrei", answer.fallback.lower())

    def test_missing_named_product_before_composition_verb_is_not_found(self):
        answer = answer_from_store(
            self.tenant,
            "Pizza Portuguesa leva frango?",
        )

        self.assertEqual(answer.intent, "product_not_found")
        self.assertIn("pizza portuguesa", answer.fallback.lower())
        self.assertIn("não encontrei", answer.fallback.lower())
        self.assertNotIn("Coca-Cola", answer.fallback)

    def test_specific_named_product_before_composition_verb_uses_description(self):
        pizzas = Category.objects.create(tenant=self.tenant, name="Pizzas")
        product = Product.objects.create(
            tenant=self.tenant,
            category=pizzas,
            name="Pizza Portuguesa QA",
            description="Presunto, mussarela, ovo, cebola, ervilha e azeitona.",
            price=Decimal("44.90"),
            is_available=True,
        )

        answer = answer_from_store(
            self.tenant,
            "Pizza Portuguesa QA leva frango?",
        )

        self.assertEqual(answer.intent, "product_description")
        self.assertIn(product.name, answer.fallback)
        self.assertIn("Presunto", answer.fallback)

    def test_contextual_o_que_ele_leva_uses_previous_product(self):
        burgers = Category.objects.create(tenant=self.tenant, name="Hambúrgueres")
        product = Product.objects.create(
            tenant=self.tenant,
            category=burgers,
            name="Hambúrguer Bacon",
            description="Pão brioche, carne, cheddar e bacon crocante.",
            price=Decimal("31.90"),
            is_available=True,
        )

        first = answer_from_store(self.tenant, "quanto custa o hamb bacon?")
        answer = answer_from_store(
            self.tenant,
            "e o que ele leva?",
            context=first.context,
        )

        self.assertEqual(answer.intent, "product_description")
        self.assertIn(product.name, answer.fallback)
        self.assertIn("bacon crocante", answer.fallback)

    def test_human_handoff_exact_phrases_still_work_after_collision_guard(self):
        for question in (
            "quero falar com uma pessoa",
            "tem alguém aí?",
            "chama um atendente",
            "quero humano",
        ):
            with self.subTest(question=question):
                answer = answer_from_store(self.tenant, question)
                self.assertEqual(answer.intent, "human")
                self.assertGreater(answer.pause_minutes, 0)
                self.assertEqual(answer.pause_reason, "human")
