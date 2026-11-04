"""No network; reconciliation may only update sandbox quarantine."""
from datetime import datetime, timezone
from unittest.mock import patch, Mock

from django.test import TestCase, override_settings

from apps.channels.connectors import ProviderError
from apps.channels.food99_webhook_reconcile import reconcile
from apps.channels.models import Connection, Inbox, Outbox, ExternalOrder, Food99StagedOrder
from apps.orders.models import Order
from apps.tenants.models import Tenant


@override_settings(SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
                   CHANNELS_LIVE_ENABLED=False, CHANNELS_NETWORK_ENABLED=False)
class Food99WebhookReconcileTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='99Food Reconciliação', slug='food99-recon',
                                            whatsapp_number='5511999991010')
        self.conn = Connection.objects.create(tenant=self.tenant, provider='99food',
                                              mode='test', merchant_id='5764619171284910575',
                                              enabled=False)
        sha = 'a' * 64
        self.event = Inbox.objects.create(
            connection=self.conn, external_id='99food-' + sha,
            order_id='5764698533651349996', code='orderNew',
            occurred_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
            state='blocked', payload={'food99_quarantined': True,
                'operational_enabled': False, 'raw_sha256': sha,
                'app_shop_id': 'vdd-food99-recon'})

    def test_preview_has_no_network_or_mutation(self):
        with patch('apps.channels.food99_webhook_reconcile.get_order_detail') as get:
            result = reconcile(self.event.pk)
            get.assert_not_called()
        self.assertFalse(result['staged'])
        self.assertFalse(result['acknowledged'])
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Food99StagedOrder.objects.exists())

    def test_apply_stages_only_and_keeps_event_blocked(self):
        row = Mock(pk=31)
        with patch('apps.channels.food99_webhook_reconcile.get_order_detail', return_value={'detail': 'private'}) as get, \
             patch('apps.channels.food99_webhook_reconcile.stage_order', return_value=(row, 'STAGED_REVIEW_REQUIRED')) as stage:
            result = reconcile(self.event.pk, apply=True)
        get.assert_called_once_with('vdd-food99-recon', '5764698533651349996')
        self.assertEqual(stage.call_args.kwargs['shop_id'], self.conn.merchant_id)
        self.assertEqual(result['state'], 'STAGED_REVIEW_REQUIRED')
        self.event.refresh_from_db()
        self.assertEqual(self.event.state, 'blocked')
        self.assertFalse(Outbox.objects.exists())
        self.assertFalse(ExternalOrder.objects.exists())
        self.assertFalse(Order.objects.exists())

    def test_foreign_shop_rejected_before_network(self):
        self.event.payload['app_shop_id'] = 'vdd-other'
        self.event.save(update_fields=['payload'])
        with patch('apps.channels.food99_webhook_reconcile.get_order_detail') as get:
            with self.assertRaises(ProviderError):
                reconcile(self.event.pk, apply=True)
            get.assert_not_called()

    def test_live_and_network_guards(self):
        for changed in ({'CHANNELS_LIVE_ENABLED': True},
                        {'CHANNELS_NETWORK_ENABLED': True},
                        {'SETTINGS_MODULE': 'config.settings.prod'},
                        {'FOOD99_SANDBOX_ENABLED': False}):
            with override_settings(**changed):
                with self.assertRaises(ProviderError):
                    reconcile(self.event.pk)

    def test_untrusted_or_processed_event_rejected(self):
        self.event.state = 'processed'
        self.event.save(update_fields=['state'])
        with self.assertRaises(ProviderError):
            reconcile(self.event.pk)
        self.event.state = 'blocked'
        self.event.payload['raw_sha256'] = 'b' * 64
        self.event.save(update_fields=['state', 'payload'])
        with self.assertRaises(ProviderError):
            reconcile(self.event.pk)

    def test_disabled_connection_necessary(self):
        self.conn.enabled = True
        self.conn.save(update_fields=['enabled'])
        with self.assertRaises(ProviderError):
            reconcile(self.event.pk)
