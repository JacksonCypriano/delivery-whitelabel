"""P27-P30 consolidated: release gates and diagnostics, no provider HTTP."""
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.channels.food99_readiness import build_readiness
from apps.channels.food99_integrity_audit import inspect_integrity
from apps.channels.food99_telemetry import build_snapshot, hml_only
from apps.channels.models import Connection, ExternalOrder, Inbox, Outbox, Food99StagedOrder
from apps.orders.models import Order
from apps.tenants.models import Tenant

HML = dict(SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
           CHANNELS_LIVE_ENABLED=False, CHANNELS_NETWORK_ENABLED=False,
           FOOD99_WEBHOOK_CAPTURE_ENABLED=True)


@override_settings(**HML)
class Food99ReleaseGateTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='P27 A', slug='p27-a', whatsapp_number='5511999992201')
        self.other = Tenant.objects.create(name='P27 B', slug='p27-b', whatsapp_number='5511999992202')
        self.conn = Connection.objects.create(tenant=self.tenant, provider='99food', mode='test', merchant_id='9271', enabled=False)
        self.other_conn = Connection.objects.create(tenant=self.other, provider='99food', mode='test', merchant_id='9272', enabled=False)
        self.order = Order.objects.create(tenant=self.tenant, source='99food', status='pending',
                                          customer_name='Fixture', total='20', subtotal='20',
                                          delivery_type='delivery', payment_flow='marketplace', payment_method='online')
        self.other_order = Order.objects.create(tenant=self.other, source='99food', status='delivered',
                                          customer_name='Fixture B', total='30', subtotal='30',
                                          delivery_type='delivery', payment_flow='marketplace', payment_method='online')
        self.ext = ExternalOrder.objects.create(connection=self.conn, order=self.order,
                                                external_id='123', delivery_by='MERCHANT', encrypted_snapshot='fixture')
        self.other_ext = ExternalOrder.objects.create(connection=self.other_conn, order=self.other_order,
                                                external_id='456', delivery_by='PLATFORM', encrypted_snapshot='fixture')

    def test_readiness_never_authorizes_production(self):
        r = build_readiness(tenant=self.tenant)
        self.assertFalse(r['release_authorized'])
        self.assertEqual(r['external_pending'], 7)
        self.assertTrue(all(c['state'] == 'external_pending' for c in r['external_checks']))
        self.assertEqual(r['order_modes'], {'MERCHANT': 1})
        self.assertNotIn('PLATFORM', r['order_modes'])

    def test_readiness_blocks_unresolved_command(self):
        Outbox.objects.create(external_order=self.ext, target='confirmed', from_status='pending',
                              state='uncertain', payload={'food99_sandbox_one_shot': True})
        r = build_readiness(tenant=self.tenant)
        self.assertEqual(r['unresolved_command_count'], 1)
        self.assertEqual(next(c for c in r['internal_checks']
                              if c['key']=='no_pending_remote_writes')['state'], 'blocked')

    def test_quarantined_webhook_is_not_error(self):
        Inbox.objects.create(connection=self.conn, external_id='p27-1', order_id='123',
                             code='orderNew', occurred_at=timezone.now(),
                             state='blocked', payload={'food99_quarantined': True})
        r = build_readiness(tenant=self.tenant)
        self.assertEqual(next(c for c in r['internal_checks']
                              if c['key']=='no_processing_errors')['state'], 'passed')

    def test_integrity_has_no_cross_tenant_leak(self):
        Outbox.objects.create(external_order=self.other_ext, target='confirmed',
                              from_status='pending', state='uncertain')
        report = inspect_integrity(tenant=self.tenant)
        self.assertEqual(report['counts']['commands'], 0)
        self.assertEqual(report['issues'], [])

    def test_integrity_detects_abandoned_and_uncertain_without_remote_calls(self):
        now = timezone.now()
        cmd = Outbox.objects.create(external_order=self.ext, target='confirmed',
                                    from_status='pending', state='sending',
                                    sent_at=now-timedelta(seconds=180),
                                    payload={'food99_sandbox_one_shot': True})
        with patch('requests.post') as post:
            report = inspect_integrity(tenant=self.tenant, now=now)
        self.assertEqual(report['issues'][0]['code'], 'STALE_SENDING')
        self.assertEqual(report['issues'][0]['command_pk'], cmd.pk)
        self.assertEqual(Outbox.objects.get(pk=cmd.pk).state, 'sending')
        post.assert_not_called()

    def test_integrity_detects_staging_shop_mismatch(self):
        Food99StagedOrder.objects.create(connection=self.conn, external_id='123',
            app_shop_id='vdd-elsewhere', fingerprint='a'*64, last_seen_status=100,
            item_count=1, amount_minor=1000, encrypted_snapshot='fixture', state='review')
        report = inspect_integrity(tenant=self.tenant)
        self.assertEqual(report['issues'][0]['code'], 'STAGING_SHOP_MISMATCH')

    def test_integrity_detects_malformed_envelope_without_crash(self):
        Inbox.objects.create(connection=self.conn, external_id='p27-2', order_id='123',
                             code='orderNew', occurred_at=timezone.now(),
                             state='error', payload=['malformed'])
        r = inspect_integrity(tenant=self.tenant)
        self.assertEqual({i['code'] for i in r['issues']},
                         {'WEBHOOK_PROCESSING_ERROR', 'INVALID_EVENT_ENVELOPE'})
        snapshot = build_snapshot(tenant=self.tenant)
        self.assertIn('integrity', snapshot)
        self.assertIn('readiness', snapshot)

    def test_bounded_limit(self):
        with self.assertRaises(ValueError):
            inspect_integrity(tenant=self.tenant, limit=0)
        with self.assertRaises(ValueError):
            inspect_integrity(tenant=self.tenant, limit=True)

    @override_settings(CHANNELS_LIVE_ENABLED=True)
    def test_live_guard_denies_reports(self):
        self.assertFalse(hml_only())
        with self.assertRaises(ValueError):
            build_readiness(tenant=self.tenant)
        with self.assertRaises(ValueError):
            inspect_integrity(tenant=self.tenant)

    @override_settings(CHANNELS_NETWORK_ENABLED=True)
    def test_generic_network_guard_denies_reports(self):
        self.assertFalse(hml_only())
        with self.assertRaises(ValueError):
            build_readiness(tenant=self.tenant)
