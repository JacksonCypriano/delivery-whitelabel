from datetime import timedelta
from decimal import Decimal

from django.test import Client, override_settings
from django.utils import timezone

from apps.core.tests_critical.base import CriticalTestCase
from apps.orders.choices import OrderSource, Status
from apps.orders.models import (
    Order,
    OrderNotificationSettings,
    OrderStatusEvent,
    OrderStatusNotification,
)
from apps.orders.operations import (
    OrderOperationError,
    allowed_transitions,
    create_manual_order,
    customer_status_reply,
    transition_order,
    update_estimate,
)
from apps.orders.realtime import _same_origin, _tenant_slug


class Package13OrderOperationTests(CriticalTestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=self.host(self.tenant_a))
        self.client.force_login(self.admin_a)

    def order(self, **kwargs):
        defaults = {
            "tenant": self.tenant_a,
            "customer_name": "Cliente",
            "customer_phone": "5511991112233",
            "subtotal": Decimal("20.00"),
            "delivery_fee": Decimal("0.00"),
            "total": Decimal("20.00"),
            "delivery_type": "pickup",
            "whatsapp_opened_at": timezone.now(),
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def test_state_machine_records_audit_estimate_and_notification_outbox(self):
        order = self.order(delivery_type="delivery")
        self.assertEqual(
            allowed_transitions(order), [Status.CONFIRMED, Status.CANCELLED]
        )

        changed, event = transition_order(
            order_id=order.pk,
            tenant=self.tenant_a,
            target_status=Status.CONFIRMED,
            actor=self.admin_a,
            prep_minutes=25,
        )
        self.assertIsNotNone(event)
        self.assertEqual(changed.status, Status.CONFIRMED)
        self.assertGreater(changed.estimated_ready_at, timezone.now())
        self.assertLess(
            changed.estimated_ready_at, timezone.now() + timedelta(minutes=26)
        )
        self.assertEqual(event.actor_id, self.admin_a.pk)
        self.assertEqual(event.from_status, Status.PENDING)
        self.assertEqual(event.to_status, Status.CONFIRMED)
        notice = OrderStatusNotification.objects.get(event=event)
        self.assertEqual(notice.recipient, "5511991112233")
        self.assertIn("confirmado", notice.text.lower())

        with self.assertRaises(OrderOperationError):
            transition_order(
                order_id=order.pk,
                tenant=self.tenant_a,
                target_status=Status.DELIVERED,
                actor=self.admin_a,
            )

    def test_pickup_never_offers_out_for_delivery(self):
        order = self.order(status=Status.READY, delivery_type="pickup")
        self.assertEqual(allowed_transitions(order), [Status.DELIVERED])

    def test_estimate_is_audited_without_changing_status(self):
        order = self.order(status=Status.PREPARING)
        changed, event = update_estimate(
            order_id=order.pk,
            tenant=self.tenant_a,
            minutes=40,
            actor=self.admin_a,
        )
        self.assertEqual(changed.status, Status.PREPARING)
        self.assertEqual(event.from_status, Status.PREPARING)
        self.assertEqual(event.to_status, Status.PREPARING)
        self.assertIn("40", event.note)

    def test_manual_order_reuses_server_pricing_stock_and_cancel_restores_stock(self):
        self.product_a.stock = Decimal("5")
        self.product_a.save(update_fields=["stock"])
        order = create_manual_order(
            tenant=self.tenant_a,
            actor=self.admin_a,
            data={
                "customer_name": "Balcão",
                "customer_phone": "",
                "delivery_type": "pickup",
                "payment_method": "cash",
                "payment_change_for": "50,00",
                "items": [{"product_id": self.product_a.pk, "quantity": 2}],
            },
        )
        self.assertEqual(order.source, OrderSource.MANUAL)
        self.assertEqual(order.total, Decimal("40.00"))
        self.assertEqual(order.items.count(), 1)
        self.assertTrue(
            OrderStatusEvent.objects.filter(
                order=order, from_status="", to_status=Status.PENDING
            ).exists()
        )
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, Decimal("3"))

        transition_order(
            order_id=order.pk,
            tenant=self.tenant_a,
            target_status=Status.CANCELLED,
            actor=self.admin_a,
        )
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, Decimal("5"))

    def test_manual_order_rejects_foreign_product(self):
        with self.assertRaises(OrderOperationError):
            create_manual_order(
                tenant=self.tenant_a,
                actor=self.admin_a,
                data={
                    "delivery_type": "pickup",
                    "payment_method": "pix",
                    "items": [{"product_id": self.product_b.pk, "quantity": 1}],
                },
            )

    def test_customer_status_is_scoped_by_tenant_and_whatsapp(self):
        order = self.order(status=Status.OUT_FOR_DELIVERY)
        text = customer_status_reply(
            tenant=self.tenant_a,
            phone="+55 (11) 99111-2233",
            question=f"onde está o pedido #{order.pk}?",
        )
        self.assertIn("saiu para entrega", text.lower())

        # Existing web orders historically store either DDD+number or +55+DDD+number.
        order.customer_phone = "11991112233"
        order.save(update_fields=["customer_phone"])
        normalized = customer_status_reply(
            tenant=self.tenant_a,
            phone="+55 (11) 99111-2233",
            question=f"pedido #{order.pk}",
        )
        self.assertIn("saiu para entrega", normalized.lower())

        wrong_phone = customer_status_reply(
            tenant=self.tenant_a,
            phone="5511888888888",
            question=f"pedido #{order.pk}",
        )
        self.assertIn("não encontrei", wrong_phone.lower())

    def test_web_checkout_draft_is_not_operational_before_customer_commit(self):
        draft = Order.objects.create(
            tenant=self.tenant_a,
            customer_name="Ainda revisando",
            customer_phone="5511991114455",
            subtotal=Decimal("20.00"),
            total=Decimal("20.00"),
            source=OrderSource.WEB,
            whatsapp_opened_at=None,
        )
        board = self.client.get("/api/merchant/orders/")
        self.assertEqual(board.status_code, 200)
        self.assertNotIn("Ainda revisando", str(board.json()))
        self.assertEqual(
            self.client.post(
                f"/api/merchant/orders/{draft.pk}/transition/",
                {"status": Status.CONFIRMED},
                content_type="application/json",
            ).status_code,
            404,
        )
        self.assertIn(
            "não encontrei",
            customer_status_reply(
                tenant=self.tenant_a,
                phone="5511991114455",
                question=f"pedido #{draft.pk}",
            ).lower(),
        )

    def test_merchant_order_endpoints_are_tenant_scoped(self):
        mine = self.order()
        foreign = Order.objects.create(
            tenant=self.tenant_b,
            customer_name="Segredo B",
            total=Decimal("99.00"),
            subtotal=Decimal("99.00"),
            whatsapp_opened_at=timezone.now(),
        )
        board = self.client.get("/api/merchant/orders/")
        self.assertEqual(board.status_code, 200, board.content)
        serialized = str(board.json())
        self.assertIn(f"'id': {mine.pk}", serialized)
        self.assertNotIn("Segredo B", serialized)
        self.assertEqual(
            self.client.get(f"/api/merchant/orders/{foreign.pk}/").status_code, 404
        )
        self.assertEqual(
            self.client.post(
                f"/api/merchant/orders/{foreign.pk}/transition/",
                {"status": Status.CONFIRMED},
                content_type="application/json",
            ).status_code,
            404,
        )

    @override_settings(MERCHANT_REACT_ENABLED=True)
    def test_legacy_order_action_is_blocked_after_react_cutover(self):
        order = self.order()
        response = self.client.post(
            "/api/merchant/resources/orders/actions/",
            {"action": "cancel_orders", "ids": [order.pk], "confirmed": "yes"},
        )
        self.assertEqual(response.status_code, 409)
        order.refresh_from_db()
        self.assertNotEqual(order.status, Status.CANCELLED)

    def test_manual_order_api_and_notification_settings(self):
        settings = self.client.post(
            "/api/merchant/orders/settings/",
            data={
                "enabled": True,
                "notify_confirmed": True,
                "notify_preparing": False,
                "notify_ready": True,
                "notify_out_for_delivery": True,
                "notify_delivered": True,
                "notify_cancelled": True,
                "default_prep_minutes": 35,
            },
            content_type="application/json",
        )
        self.assertEqual(settings.status_code, 200, settings.content)
        config = OrderNotificationSettings.objects.get(tenant=self.tenant_a)
        self.assertEqual(config.default_prep_minutes, 35)
        self.assertFalse(config.notify_preparing)

        response = self.client.post(
            "/api/merchant/orders/manual/",
            data={
                "customer_name": "Telefone",
                "delivery_type": "pickup",
                "payment_method": "pix",
                "items": [{"product_id": self.product_a.pk, "quantity": 1}],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        order = Order.objects.get(pk=response.json()["id"])
        self.assertEqual(order.tenant_id, self.tenant_a.pk)
        self.assertEqual(order.source, OrderSource.MANUAL)

    def test_websocket_origin_and_tenant_host_helpers(self):
        self.assertEqual(_tenant_slug("alpha.lvh.me"), "alpha")
        self.assertEqual(_tenant_slug("alpha.lvh.me:8000"), "alpha")
        self.assertFalse(_same_origin({"host": "alpha.lvh.me"}))
        self.assertFalse(
            _same_origin({"host": "alpha.lvh.me", "origin": "https://evil.example"})
        )
        self.assertTrue(
            _same_origin({"host": "alpha.lvh.me", "origin": "https://alpha.lvh.me"})
        )
