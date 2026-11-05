"""Pacote 23: contract-level tests for pickup and platform fulfillment.

No provider network traffic. Real pickup/platform certification is still pending.
"""
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.channels.food99_local_sync import sync_existing
from apps.channels.food99_sandbox_actions import (
    permitted_sandbox,
    queue_sandbox_transition,
    send_reserved_action,
)
from apps.channels.models import Connection, ExternalOrder, Inbox, Outbox
from apps.orders.models import Order
from apps.orders.operations import OrderOperationError
from apps.tenants.models import Tenant

FLAGS = dict(
    SETTINGS_MODULE="config.settings.hml",
    FOOD99_SANDBOX_ENABLED=True,
    FOOD99_SANDBOX_ACTIONS_ENABLED=True,
    FOOD99_WEBHOOK_CAPTURE_ENABLED=True,
    FOOD99_WEBHOOK_ACK_ENABLED=True,
    FOOD99_ASYNC_RECONCILE_ENABLED=True,
    FOOD99_LOCAL_EVENT_SYNC_ENABLED=True,
    FOOD99_SANDBOX_IMPORT_TO_ORDERS=True,
    FOOD99_PILOT_TENANT_SLUG="vitrine-demo",
    CHANNELS_LIVE_ENABLED=False,
    CHANNELS_NETWORK_ENABLED=False,
    FOOD99_AUTO_PILOT_ENABLED=False,
)


@override_settings(**FLAGS)
class Food99FulfillmentP23Tests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Sandbox Pickup", slug="vitrine-demo", whatsapp_number="5511999991111"
        )
        self.connection = Connection.objects.create(
            tenant=self.tenant,
            provider="99food",
            mode="test",
            merchant_id="5764619171284910575",
            enabled=False,
        )
        self.order = Order.objects.create(
            tenant=self.tenant,
            source="99food",
            status="confirmed",
            customer_name="Cliente de teste",
            total="25.00",
            subtotal="25.00",
            delivery_type="pickup",
            payment_flow="marketplace",
            payment_method="online",
        )
        self.external = ExternalOrder.objects.create(
            connection=self.connection,
            order=self.order,
            external_id="5764698851357296409",
            delivery_by="CUSTOMER",
            encrypted_snapshot="sandbox-test",
        )

    def event(self, code):
        digest = f"{Inbox.objects.count() + 1:064x}"
        return Inbox.objects.create(
            connection=self.connection,
            external_id="99food-" + digest,
            order_id=self.external.external_id,
            code=code,
            state="blocked",
            occurred_at=timezone.now(),
            payload={
                "food99_quarantined": True,
                "operational_enabled": False,
                "app_shop_id": "vdd-vitrine-demo",
                "raw_sha256": digest,
            },
        )

    def test_pickup_ready_webhook_maps_to_ready_for_pickup(self):
        event = self.event("orderReady")
        result = sync_existing(event.pk, apply=True)
        self.order.refresh_from_db()
        self.assertEqual(result["result"], "UPDATED")
        self.assertEqual(self.order.status, "ready_for_pickup")
        self.assertIn("delivered", permitted_sandbox(self.order))

    def test_pickup_finish_is_reserved_once_and_never_optimistic(self):
        self.order.status = "ready_for_pickup"
        self.order.save(update_fields=["status"])
        with patch("apps.channels.tasks.send_99food_sandbox_action.delay") as task:
            with self.captureOnCommitCallbacks(execute=True):
                queue_sandbox_transition(self.order.pk, self.tenant, "delivered")
        command = Outbox.objects.get()
        self.assertEqual(command.payload["food99_sandbox_action"], "finish")
        self.assertEqual(command.state, "pending")
        task.assert_called_once_with(command.pk)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "ready_for_pickup")
        with self.assertRaises(OrderOperationError):
            queue_sandbox_transition(self.order.pk, self.tenant, "delivered")

    def test_pickup_finish_one_post_then_signed_finish_event(self):
        self.order.status = "ready_for_pickup"
        self.order.save(update_fields=["status"])
        command = Outbox.objects.create(
            external_order=self.external,
            target="delivered",
            from_status="ready_for_pickup",
            payload={"food99_sandbox_action": "finish"},
            state="pending",
        )
        with patch("apps.channels.food99_orders.get_order_detail", return_value={
            "status": 200, "cancel_time": 0, "complete_time": 0
        }), patch("apps.channels.food99_auth.get_shop_token", return_value="fake"), patch(
            "requests.post",
            return_value=Mock(status_code=200, json=lambda: {"errno": 0, "data": {}}),
        ) as post:
            result = send_reserved_action(command.pk)
            self.assertEqual(result["result"], "AWAITING_WEBHOOK")
            self.assertFalse(send_reserved_action(command.pk)["sent"])
            post.assert_called_once()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "ready_for_pickup")
        event = self.event("orderFinish")
        sync_existing(event.pk, apply=True)
        self.order.refresh_from_db()
        command.refresh_from_db()
        self.assertEqual(self.order.status, "delivered")
        self.assertEqual(command.state, "confirmed")

    def test_platform_delivery_does_not_offer_dispatch_or_finish(self):
        self.external.delivery_by = "PLATFORM"
        self.external.save(update_fields=["delivery_by"])
        self.order.delivery_type = "delivery"
        self.order.status = "ready"
        self.order.save(update_fields=["delivery_type", "status"])
        transitions = permitted_sandbox(self.order)
        self.assertNotIn("out_for_delivery", transitions)
        self.assertNotIn("delivered", transitions)
        with self.assertRaises(OrderOperationError):
            queue_sandbox_transition(self.order.pk, self.tenant, "delivered")
        self.assertFalse(Outbox.objects.exists())

    def test_delivery_status_requires_review_and_cannot_deliver(self):
        self.external.delivery_by = "PLATFORM"
        self.external.save(update_fields=["delivery_by"])
        self.order.delivery_type = "delivery"
        self.order.status = "ready"
        self.order.save(update_fields=["delivery_type", "status"])
        event = self.event("deliveryStatus")
        result = sync_existing(event.pk, apply=True)
        self.assertEqual(result["result"], "REVIEW_REQUIRED")
        self.order.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(self.order.status, "ready")
        self.assertEqual(event.state, "blocked")

    def test_cancel_and_finish_are_not_interchangeable(self):
        self.order.status = "cancelled"
        self.order.save(update_fields=["status"])
        event = self.event("orderFinish")
        result = sync_existing(event.pk, apply=True)
        self.assertEqual(result["result"], "TERMINAL_CONFLICT")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")
