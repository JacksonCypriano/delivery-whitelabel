"""P24.1: one-shot confirmation remains idempotent after webhook/state changes."""
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.channels.food99_auto_pilot import auto_pilot_order_new
from apps.channels.food99_remote_confirm import confirm_existing
from apps.channels.models import Connection, ExternalOrder, Food99StagedOrder, Inbox, Outbox
from apps.orders.models import Order
from apps.tenants.models import Tenant

FLAGS = dict(
    SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
    CHANNELS_LIVE_ENABLED=False, CHANNELS_NETWORK_ENABLED=False,
    FOOD99_AUTO_PILOT_ENABLED=True, FOOD99_PILOT_BRL_CONFIRMED=True,
    FOOD99_SANDBOX_IMPORT_TO_ORDERS=True, FOOD99_REMOTE_CONFIRM_ENABLED=True,
    FOOD99_WEBHOOK_ACK_ENABLED=True, FOOD99_WEBHOOK_CAPTURE_ENABLED=True,
    FOOD99_ASYNC_RECONCILE_ENABLED=True,
    FOOD99_PILOT_TENANT_SLUG='p24-idempotency',
)


@override_settings(**FLAGS)
class Food99IdempotencyP241Tests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='P24 Idempotency', slug='p24-idempotency',
            whatsapp_number='5511999998899',
        )
        self.connection = Connection.objects.create(
            tenant=self.tenant, provider='99food', mode='test',
            enabled=False, merchant_id='555',
        )
        self.order = Order.objects.create(
            tenant=self.tenant, source='99food', status='confirmed',
            customer_name='Sandbox', total='21', subtotal='21',
            delivery_type='delivery', payment_flow='marketplace',
            payment_method='online',
        )
        self.external = ExternalOrder.objects.create(
            connection=self.connection, order=self.order,
            external_id='123456789', delivery_by='MERCHANT',
            encrypted_snapshot='test',
        )
        sha = 'a' * 64
        self.event = Inbox.objects.create(
            connection=self.connection, order_id=self.external.external_id,
            code='orderNew', external_id='99food-' + sha, state='blocked',
            occurred_at=timezone.now(), payload={
                'food99_quarantined': True, 'operational_enabled': False,
                'app_shop_id': 'vdd-p24-idempotency', 'raw_sha256': sha,
            },
        )
        self.staged = Food99StagedOrder.objects.create(
            connection=self.connection, external_id=self.external.external_id,
            app_shop_id='vdd-p24-idempotency', fingerprint='f' * 64,
            latest_fingerprint='f' * 64, last_seen_status=100,
            item_count=1, amount_minor=2100, encrypted_snapshot='test',
            state='reviewed',
        )

    def reserve(self, state):
        return Outbox.objects.create(
            external_order=self.external, target='confirmed',
            from_status='pending', state=state, attempts=1,
            payload={'food99_sandbox_one_shot': True},
        )

    def test_confirm_existing_returns_already_requested_after_confirm_webhook(self):
        self.reserve('confirmed')
        with patch('apps.channels.food99_remote_confirm._eligible_order') as eligibility, \
             patch('apps.channels.food99_remote_confirm.get_order_detail') as fetch, \
             patch('apps.channels.food99_remote_confirm._remote_confirm') as post:
            result = confirm_existing(order_id=self.order.pk, apply=True, confirm_remote=True)
        self.assertEqual(result['result'], 'ALREADY_REQUESTED')
        self.assertFalse(result['sent'])
        eligibility.assert_not_called()
        fetch.assert_not_called()
        post.assert_not_called()
        self.assertEqual(Outbox.objects.count(), 1)

    def test_confirm_does_not_retry_any_reserved_state(self):
        for state in ('sending', 'awaiting', 'uncertain', 'confirmed'):
            with self.subTest(state=state):
                Outbox.objects.all().delete()
                self.reserve(state)
                with patch('apps.channels.food99_remote_confirm.get_order_detail') as fetch, \
                     patch('apps.channels.food99_remote_confirm._remote_confirm') as post:
                    result = confirm_existing(order_id=self.order.pk, apply=True, confirm_remote=True)
                self.assertEqual(result['result'], 'ALREADY_REQUESTED')
                fetch.assert_not_called()
                post.assert_not_called()
                self.assertEqual(Outbox.objects.count(), 1)

    def test_auto_pilot_duplicate_never_fetches_or_confirms(self):
        self.reserve('confirmed')
        with patch('apps.channels.food99_auto_pilot.get_order_detail') as fetch, \
             patch('apps.channels.food99_auto_pilot.promote_reviewed') as promote, \
             patch('apps.channels.food99_auto_pilot.confirm_existing') as confirm:
            result = auto_pilot_order_new(self.event.pk, staged_id=self.staged.pk)
        self.assertEqual(result['result'], 'ALREADY_REQUESTED')
        self.assertEqual(result['order_id'], self.order.pk)
        self.assertFalse(result['imported'])
        fetch.assert_not_called()
        promote.assert_not_called()
        confirm.assert_not_called()

    def test_auto_pilot_uncertain_confirmation_never_replayed(self):
        self.reserve('uncertain')
        with patch('apps.channels.food99_auto_pilot.get_order_detail') as fetch, \
             patch('apps.channels.food99_auto_pilot.confirm_existing') as confirm:
            result = auto_pilot_order_new(self.event.pk, staged_id=self.staged.pk)
        self.assertEqual(result['result'], 'ALREADY_REQUESTED')
        fetch.assert_not_called()
        confirm.assert_not_called()

    def test_other_tenant_cannot_access_its_order_via_duplicate_event(self):
        with override_settings(FOOD99_PILOT_TENANT_SLUG='other-tenant'):
            from apps.channels.connectors import ProviderError
            with self.assertRaises(ProviderError):
                auto_pilot_order_new(self.event.pk, staged_id=self.staged.pk)

    def test_duplicate_inbox_same_provider_event_has_db_unique_constraint(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Inbox.objects.create(
                    connection=self.connection, order_id=self.event.order_id,
                    code='orderNew', external_id=self.event.external_id,
                    occurred_at=timezone.now(), payload=self.event.payload,
                )
        self.assertEqual(Inbox.objects.filter(connection=self.connection).count(), 1)
