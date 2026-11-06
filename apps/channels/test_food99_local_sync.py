"""Regression tests for sandbox webhook -> existing Order/KDS projection."""
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.channels.connectors import ProviderError
from apps.channels.food99_local_sync import sync_existing, sync_batch
from apps.channels.models import Connection, ExternalOrder, Inbox, Outbox
from apps.orders.models import Order, OrderStatusEvent
from apps.tenants.models import Tenant

FLAGS = dict(SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
             CHANNELS_LIVE_ENABLED=False, CHANNELS_NETWORK_ENABLED=False,
             FOOD99_SANDBOX_IMPORT_TO_ORDERS=True,
             FOOD99_LOCAL_EVENT_SYNC_ENABLED=True)


@override_settings(**FLAGS)
class Food99LocalSyncTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Sandbox Sync', slug='sandbox-sync',
                                            whatsapp_number='5511999991111')
        self.connection = Connection.objects.create(
            tenant=self.tenant, provider='99food', mode='test', enabled=False,
            merchant_id='123456789')
        self.order = Order.objects.create(
            tenant=self.tenant, source='99food', status='pending',
            customer_name='Cliente 99Food', total='21.00', subtotal='20.00',
            delivery_fee='1.00', delivery_type='delivery', payment_flow='marketplace',
            payment_method='online')
        self.external = ExternalOrder.objects.create(
            connection=self.connection, order=self.order,
            external_id='5764698533651349996', encrypted_snapshot='sandbox-test')

    def make_event(self, kind='orderConfirm', *, seconds=0, digest=None):
        digest = digest or ('a' * 63 + str(Inbox.objects.count() % 10))
        return Inbox.objects.create(
            connection=self.connection, external_id='99food-' + digest,
            order_id=self.external.external_id, code=kind, state='blocked',
            occurred_at=timezone.now() + timedelta(seconds=seconds),
            payload={'food99_quarantined': True, 'operational_enabled': False,
                     'app_shop_id': 'vdd-' + self.tenant.slug, 'raw_sha256': digest})

    def test_preview_leaves_order_and_inbox_unchanged(self):
        event = self.make_event()
        result = sync_existing(event.pk)
        self.assertEqual(result['result'], 'PREVIEW')
        self.order.refresh_from_db(); event.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')
        self.assertEqual(event.state, 'blocked')

    @patch('apps.channels.food99_local_sync.publish_order_event')
    def test_signed_confirm_updates_existing_order_once(self, publish):
        event = self.make_event()
        with self.captureOnCommitCallbacks(execute=True):
            result = sync_existing(event.pk, apply=True)
        self.assertTrue(result['applied'])
        self.order.refresh_from_db(); event.refresh_from_db()
        self.assertEqual(self.order.status, 'confirmed')
        self.assertEqual(event.state, 'processed')
        self.assertEqual(OrderStatusEvent.objects.filter(order=self.order).count(), 1)
        publish.assert_called_once_with(self.order.pk, self.tenant.pk)
        self.assertEqual(sync_existing(event.pk, apply=True)['result'], 'ALREADY_HANDLED')
        self.assertEqual(OrderStatusEvent.objects.filter(order=self.order).count(), 1)

    def test_remote_confirmation_receipt_resolves_one_shot_command(self):
        Outbox.objects.create(external_order=self.external, target='confirmed',
                              from_status='pending', state='awaiting',
                              payload={'food99_sandbox_one_shot': True})
        event = self.make_event('orderConfirm')
        sync_existing(event.pk, apply=True)
        self.assertEqual(Outbox.objects.get().state, 'confirmed')

    def test_terminal_cancellation_supersedes_pending_command(self):
        Outbox.objects.create(external_order=self.external, target='confirmed',
                              from_status='pending', state='awaiting', payload={})
        event = self.make_event('orderCancel')
        sync_existing(event.pk, apply=True)
        self.assertEqual(Outbox.objects.get().state, 'superseded')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')

    def test_unknown_event_is_not_applied(self):
        event = self.make_event('orderNew')
        self.assertEqual(sync_existing(event.pk, apply=True)['result'], 'REVIEW_REQUIRED')
        event.refresh_from_db()
        self.assertEqual(event.state, 'blocked')

    def test_unimported_order_never_created(self):
        event = self.make_event()
        self.external.delete()
        self.assertEqual(sync_existing(event.pk, apply=True)['result'], 'NOT_IMPORTED')
        self.assertEqual(Order.objects.count(), 1)

    def test_terminal_order_cannot_reopen(self):
        self.order.status = 'cancelled'; self.order.save(update_fields=['status'])
        event = self.make_event('orderConfirm')
        self.assertEqual(sync_existing(event.pk, apply=True)['result'], 'TERMINAL_CONFLICT')
        event.refresh_from_db()
        self.assertEqual(event.state, 'blocked')

    def test_old_provider_event_is_ignored(self):
        self.external.last_event_at = timezone.now()
        self.external.save(update_fields=['last_event_at'])
        event = self.make_event('orderReady', seconds=-120)
        self.assertEqual(sync_existing(event.pk, apply=True)['result'], 'STALE')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_newer_regression_is_ignored(self):
        self.order.status = 'ready'; self.order.save(update_fields=['status'])
        event = self.make_event('orderConfirm')
        self.assertEqual(sync_existing(event.pk, apply=True)['result'], 'REGRESSION')

    def test_shop_or_signature_metadata_mismatch_is_rejected(self):
        event = self.make_event()
        event.payload['app_shop_id'] = 'vdd-other'
        event.save(update_fields=['payload'])
        with self.assertRaises(ProviderError):
            sync_existing(event.pk, apply=True)

    def test_disabled_gate_never_updates(self):
        event = self.make_event()
        with override_settings(FOOD99_LOCAL_EVENT_SYNC_ENABLED=False):
            with self.assertRaises(ProviderError):
                sync_existing(event.pk, apply=True)

    def test_disabled_connection_required(self):
        event = self.make_event()
        self.connection.enabled = True; self.connection.save(update_fields=['enabled'])
        with self.assertRaises(ProviderError):
            sync_existing(event.pk, apply=True)

    def test_batch_limits_and_isolation(self):
        self.make_event()
        self.assertEqual(sync_batch(tenant_slug=self.tenant.slug, limit=1)['selected'], 1)
        self.assertEqual(sync_batch(tenant_slug='unknown')['selected'], 0)
        for limit in (0, 101, True, '1'):
            with self.assertRaises(ProviderError):
                sync_batch(tenant_slug=self.tenant.slug, limit=limit)
