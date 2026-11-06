from decimal import Decimal
from django.test import Client
from django.utils import timezone
from apps.core.tests_critical.base import CriticalTestCase
from apps.orders.choices import Status, OrderSource
from apps.orders.models import Order, OrderItem, OrderNotificationSettings, OrderStatusNotification
from apps.orders.operations import transition_order, allowed_transitions, customer_status_reply, OrderOperationError


class Package14OperationsTests(CriticalTestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=self.host(self.tenant_a))
        self.client.force_login(self.admin_a)

    def order(self, **kwargs):
        defaults = dict(tenant=self.tenant_a, customer_name="Cliente", customer_phone="5511991112233",
                        subtotal=Decimal("20"), total=Decimal("20"), delivery_fee=0,
                        delivery_type="pickup", source=OrderSource.MANUAL, status=Status.PREPARING)
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def transition(self, order, status, **kwargs):
        return transition_order(order_id=order.pk, tenant=self.tenant_a, target_status=status, actor=self.admin_a, **kwargs)

    def post(self, order, data):
        return self.client.post(f"/api/merchant/orders/{order.pk}/transition/", data, content_type="application/json")

    def test_pickup_real_status_and_outbox_audit(self):
        order = self.order()
        self.assertEqual(allowed_transitions(order), [Status.READY_FOR_PICKUP])
        changed, event = self.transition(order, Status.READY_FOR_PICKUP)
        self.assertEqual(changed.status, "ready_for_pickup")
        self.assertEqual(event.actor, self.admin_a)
        self.assertEqual(event.tenant, self.tenant_a)
        self.assertEqual(event.from_status, Status.PREPARING)
        self.assertIn("Você já pode vir buscar", event.notification.text)
        self.assertIsNotNone(changed.estimated_fulfillment_at)
        self.assertEqual(allowed_transitions(changed), [Status.DELIVERED])

    def test_delivery_cannot_use_pickup_state(self):
        order = self.order(delivery_type="delivery")
        with self.assertRaises(OrderOperationError): self.transition(order, Status.READY_FOR_PICKUP)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.PREPARING)
        self.assertFalse(order.status_events.exists())

    def test_pickup_cannot_go_out_for_delivery(self):
        order = self.order(status=Status.READY_FOR_PICKUP)
        self.assertEqual(self.post(order, {"status": Status.OUT_FOR_DELIVERY}).status_code, 400)

    def test_old_ready_client_normalized_and_duplicate_does_not_enqueue(self):
        order = self.order()
        self.assertEqual(self.post(order, {"status": "ready"}).status_code, 200)
        self.assertEqual(self.post(order, {"status": "ready"}).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.READY_FOR_PICKUP)
        self.assertEqual(order.status_events.count(), 1)
        self.assertEqual(OrderStatusNotification.objects.count(), 1)

    def test_historical_pickup_ready_still_completes(self):
        order = self.order(status=Status.READY)
        self.assertIsNone(self.transition(order, Status.READY)[1])
        self.assertEqual(self.transition(order, Status.DELIVERED)[0].status, Status.DELIVERED)

    def test_board_contains_all_details_and_no_finished_orders(self):
        order = self.order()
        OrderItem.objects.bulk_create([OrderItem(order=order, name=f"Item {n}", quantity=1, price=2,
            notes="Sem sal", combination_details={"customizations": [{"option_name": "Molho"}]}) for n in range(9)])
        self.order(status=Status.DELIVERED)
        self.order(status=Status.CANCELLED)
        self.order(tenant=self.tenant_b)
        response = self.client.get("/api/merchant/orders/?active_only=1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["finished"], [])
        cards = [card for col in data["columns"] for card in col["orders"]]
        self.assertEqual([card["id"] for card in cards], [order.pk])
        self.assertEqual(len(cards[0]["items"]), 9)
        self.assertEqual(cards[0]["items"][0]["notes"], "Sem sal")
        self.assertTrue(cards[0]["items"][0]["combination_details"])
        self.assertEqual(len(self.client.get("/api/merchant/orders/").json()["finished"]), 2)

    def test_delivered_disappears_but_is_still_in_history(self):
        order = self.order(status=Status.READY_FOR_PICKUP)
        self.transition(order, Status.DELIVERED)
        data = self.client.get("/api/merchant/orders/?active_only=1").json()
        self.assertFalse(any(col["orders"] for col in data["columns"]))
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(self.client.get(f"/api/merchant/orders/{order.pk}/").status_code, 200)

    def test_delivery_default_and_manual_estimate(self):
        OrderNotificationSettings.objects.create(tenant=self.tenant_a, default_delivery_minutes=45)
        for supplied, expected in [(None, 45), (55, 55)]:
            order = self.order(status=Status.READY, delivery_type="delivery")
            changed, event = self.transition(order, Status.OUT_FOR_DELIVERY, fulfillment_minutes=supplied)
            delta = (changed.estimated_fulfillment_at - timezone.now()).total_seconds()
            self.assertAlmostEqual(delta, expected * 60, delta=3)
            self.assertEqual(event.metadata["fulfillment_minutes"], expected)
            self.assertIn("Previsão de entrega", event.notification.text)

    def test_pickup_default_does_not_replace_manual_on_preparation(self):
        order = self.order(status=Status.PENDING)
        changed, event = self.transition(order, Status.CONFIRMED, fulfillment_minutes=55)
        estimate = changed.estimated_fulfillment_at
        changed, _ = self.transition(order, Status.PREPARING)
        self.assertEqual(changed.estimated_fulfillment_at, estimate)
        self.assertEqual(event.metadata["fulfillment_minutes"], 55)

    def test_edited_message_and_complement_saved_in_outbox_and_detail(self):
        order = self.order()
        _, event = self.transition(order, Status.READY_FOR_PICKUP, message="Olá, pode vir!", complement="Entrada lateral.")
        self.assertEqual(event.notification.text, "Olá, pode vir!\nEntrada lateral.")
        detail = self.client.get(f"/api/merchant/orders/{order.pk}/").json()
        self.assertEqual(detail["events"][0]["notification"]["text"], event.notification.text)
        self.assertEqual(detail["events"][0]["metadata"]["message"], event.notification.text)

    def test_skip_notification_still_records_decision(self):
        order = self.order()
        _, event = self.transition(order, Status.READY_FOR_PICKUP, send_notification=False)
        self.assertFalse(event.metadata["send_notification"])
        self.assertFalse(OrderStatusNotification.objects.exists())

    def test_skip_forbidden_by_store(self):
        OrderNotificationSettings.objects.create(tenant=self.tenant_a, allow_skip_notification=False)
        order = self.order()
        self.assertEqual(self.post(order, {"status": Status.READY_FOR_PICKUP, "send_notification": False}).status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.PREPARING)

    def test_cannot_force_disabled_notification(self):
        OrderNotificationSettings.objects.create(tenant=self.tenant_a, notify_ready=False)
        self.transition(self.order(), Status.READY_FOR_PICKUP, send_notification=True)
        self.assertFalse(OrderStatusNotification.objects.exists())

    def test_invalid_fields_do_not_change_order(self):
        for data in [{"send_notification": "false"}, {"fulfillment_minutes": True},
                     {"fulfillment_minutes": 10.5}, {"fulfillment_minutes": 241},
                     {"message": ["invalid"]}, {"message": "a" * 2001}, {"complement": "a" * 501}]:
            order = self.order()
            response = self.post(order, {"status": Status.READY_FOR_PICKUP, **data})
            self.assertEqual(response.status_code, 400, response.content)
            order.refresh_from_db()
            self.assertEqual(order.status, Status.PREPARING)
            self.assertFalse(order.status_events.exists())

    def test_tenant_is_taken_from_host_not_payload(self):
        foreign = self.order(tenant=self.tenant_b)
        response = self.post(foreign, {"status": Status.READY_FOR_PICKUP, "tenant": self.tenant_b.pk})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(foreign.status_events.exists())

    def test_configuration_persists_and_validates_all_deadlines(self):
        path = "/api/merchant/orders/settings/"
        self.assertEqual(self.client.post(path, {"default_delivery_minutes": 55, "default_pickup_minutes": 25}, content_type="application/json").status_code, 200)
        self.assertEqual(self.client.get(path).json()["default_delivery_minutes"], 55)
        for invalid in [None, True, 3, 241, 5.2]:
            self.assertEqual(self.client.post(path, {"default_delivery_minutes": invalid}, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.get(path).json()["default_delivery_minutes"], 55)

    def test_agent_reads_pickup_state_and_delivery_deadline(self):
        order = self.order(status=Status.READY_FOR_PICKUP)
        self.assertIn("pronto para retirada", customer_status_reply(tenant=self.tenant_a, phone=order.customer_phone))
        order.status = Status.READY
        order.delivery_type = "delivery"
        order.save()
        self.transition(order, Status.OUT_FOR_DELIVERY, fulfillment_minutes=55)
        self.assertIn("Previsão de entrega", customer_status_reply(tenant=self.tenant_a, phone=order.customer_phone))

    def test_drafts_and_abandoned_orders_stay_out_of_operation(self):
        self.order(source=OrderSource.WEB, whatsapp_opened_at=None)
        self.order(abandoned_at=timezone.now())
        data = self.client.get("/api/merchant/orders/?active_only=1").json()
        self.assertFalse(any(col["orders"] for col in data["columns"]))

    def test_anonymous_and_foreign_users_cannot_read_operation(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/merchant/orders/?active_only=1").status_code, 401)
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get("/api/merchant/orders/?active_only=1").status_code, 403)

    def test_csrf_required_for_status_mutation(self):
        client = Client(HTTP_HOST=self.host(self.tenant_a), enforce_csrf_checks=True)
        client.force_login(self.admin_a)
        order = self.order()
        response = client.post(f"/api/merchant/orders/{order.pk}/transition/", {"status": Status.READY_FOR_PICKUP}, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, Status.PREPARING)

    def test_manual_preparation_estimate_is_in_edited_message(self):
        order = self.order(status=Status.PENDING, delivery_type="delivery")
        _, event = self.transition(order, Status.CONFIRMED, prep_minutes=50, message="Recebemos seu pedido.")
        self.assertIn("Previsão para ficar pronto", event.notification.text)
        self.assertEqual(event.metadata["prep_minutes"], 50)
