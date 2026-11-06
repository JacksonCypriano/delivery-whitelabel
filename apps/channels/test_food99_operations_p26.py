"""Package 26: safe diagnostics, tenant isolation and command crash recovery."""
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.channels.connectors import ProviderError
from apps.channels.food99_telemetry import build_snapshot, hml_only
from apps.channels.food99_recovery import recover_stale_sending
from apps.channels.models import Connection, ExternalOrder, Food99StagedOrder, Inbox, Outbox
from apps.orders.models import Order
from apps.tenants.models import Tenant

HML = dict(SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
           CHANNELS_NETWORK_ENABLED=False, CHANNELS_LIVE_ENABLED=False)


@override_settings(**HML)
class Food99OperationsP26Tests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.tenant = Tenant.objects.create(name='P26 Loja A', slug='p26-a', whatsapp_number='5511999888001')
        self.other = Tenant.objects.create(name='P26 Loja B', slug='p26-b', whatsapp_number='5511999888002')
        self.connection = Connection.objects.create(tenant=self.tenant, provider='99food', mode='test', merchant_id='999901', enabled=False)
        self.other_connection = Connection.objects.create(tenant=self.other, provider='99food', mode='test', merchant_id='999902', enabled=False)
        self.order = Order.objects.create(tenant=self.tenant, source='99food', status='pending', customer_name='Test A', total='21', subtotal='21', delivery_type='delivery', payment_flow='marketplace', payment_method='online')
        self.other_order = Order.objects.create(tenant=self.other, source='99food', status='pending', customer_name='Test B', total='22', subtotal='22', delivery_type='delivery', payment_flow='marketplace', payment_method='online')
        self.external = ExternalOrder.objects.create(connection=self.connection, order=self.order, external_id='111', encrypted_snapshot='redacted')
        self.other_external = ExternalOrder.objects.create(connection=self.other_connection, order=self.other_order, external_id='222', encrypted_snapshot='redacted')

    def command(self, external=None, state='sending', age=150):
        return Outbox.objects.create(external_order=external or self.external, target='confirmed',
            from_status='pending', payload={'food99_sandbox_one_shot': True},
            state=state, attempts=1, sent_at=self.now - timedelta(seconds=age))

    def event(self, connection=None, state='blocked', quarantined=True, order_id='111'):
        return Inbox.objects.create(connection=connection or self.connection, external_id='e'+order_id,
            order_id=order_id, code='orderNew', occurred_at=self.now,
            payload={'food99_quarantined': quarantined}, state=state)

    def test_read_only_and_tenant_isolation(self):
        self.command()
        self.command(external=self.other_external)
        self.event()
        self.event(connection=self.other_connection, order_id='222')
        with patch('apps.channels.food99_telemetry.timezone.now', return_value=self.now):
            data = build_snapshot(tenant=self.tenant, now=self.now)
        self.assertEqual(data['outbox']['total'], 1)
        self.assertEqual(data['inbox']['total'], 1)
        self.assertEqual(data['imported_count'], 1)
        self.assertEqual(len(data['alerts']), 1)
        self.assertEqual(data['alerts'][0]['external_id'], '111')
        self.assertNotIn('222', str(data))
        self.assertEqual(Outbox.objects.filter(state='sending').count(), 2)

    def test_blocked_quarantine_not_error(self):
        self.event()
        data = build_snapshot(tenant=self.tenant, now=self.now)
        self.assertEqual(data['inbox']['states']['blocked'], 1)
        self.assertEqual(data['alerts'], [])

    def test_uncertain_and_delayed_alerts(self):
        self.command(state='uncertain', age=10)
        data = build_snapshot(tenant=self.tenant, now=self.now)
        self.assertEqual(data['alerts'][0]['code'], 'REMOTE_OUTCOME_UNKNOWN')
        self.assertIn('não reenviar', data['alerts'][0]['action'])

    def test_preview_is_noop_and_scoped(self):
        self.command()
        self.command(external=self.other_external)
        report = recover_stale_sending(tenant_slug=self.tenant.slug, now=self.now)
        self.assertEqual(report['mode'], 'preview')
        self.assertEqual(len(report['candidate_ids']), 1)
        self.assertEqual(Outbox.objects.filter(state='sending').count(), 2)

    def test_apply_does_not_post_and_is_idempotent(self):
        self.command()
        with patch('requests.post') as remote:
            report = recover_stale_sending(tenant_slug=self.tenant.slug, apply=True, now=self.now)
            again = recover_stale_sending(tenant_slug=self.tenant.slug, apply=True, now=self.now)
        self.assertEqual(report['updated'], 1)
        self.assertEqual(again['updated'], 0)
        self.assertEqual(Outbox.objects.get(external_order=self.external).state, 'uncertain')
        remote.assert_not_called()

    def test_fresh_and_other_command_types_untouched(self):
        self.command(age=30)
        report = recover_stale_sending(tenant_slug=self.tenant.slug, apply=True, now=self.now)
        self.assertEqual(report['updated'], 0)
        self.assertEqual(Outbox.objects.get(external_order=self.external).state, 'sending')

    @override_settings(CHANNELS_NETWORK_ENABLED=True)
    def test_recovery_refuses_generic_network_mode(self):
        self.command()
        with self.assertRaises(ProviderError):
            recover_stale_sending(tenant_slug=self.tenant.slug, apply=True, now=self.now)
        self.assertEqual(Outbox.objects.get(external_order=self.external).state, 'sending')

    @override_settings(SETTINGS_MODULE='config.settings.prod')
    def test_production_guard(self):
        self.assertFalse(hml_only())
        with self.assertRaises(ProviderError):
            recover_stale_sending(tenant_slug=self.tenant.slug, apply=True, now=self.now)

    def test_no_cross_tenant_staging_in_report(self):
        for conn, suffix in ((self.connection, 'a'), (self.other_connection, 'b')):
            Food99StagedOrder.objects.create(connection=conn, external_id=suffix,
                app_shop_id='vdd-'+conn.tenant.slug, fingerprint='a'*64,
                last_seen_status=100, item_count=1, amount_minor=123,
                encrypted_snapshot='redacted', state='review')
        data = build_snapshot(tenant=self.tenant, now=self.now + timedelta(minutes=7))
        self.assertEqual(data['staging']['total'], 1)
        self.assertEqual(data['alerts'][0]['external_id'], 'a')

    def test_delivery_awaiting_has_specific_sandbox_alert(self):
        self.order.status = 'out_for_delivery'
        self.order.save(update_fields=['status'])
        Outbox.objects.create(external_order=self.external, target='delivered',
            from_status='out_for_delivery', state='awaiting', attempts=1,
            sent_at=self.now - timedelta(seconds=15))
        report = build_snapshot(tenant=self.tenant, now=self.now)
        self.assertEqual(report['alerts'][0]['code'], 'DELIVERY_CONFIRMATION_PENDING')
        self.assertIn('não', report['alerts'][0]['action'].lower())
        from apps.channels.services import presentation
        data = presentation(self.order)
        self.assertTrue(data['food99_delivery_pending'])
        self.assertEqual(data['sync_target'], 'delivered')

    def test_delivery_alert_isolated_from_other_tenant(self):
        Outbox.objects.create(external_order=self.other_external, target='delivered',
            from_status='out_for_delivery', state='awaiting', attempts=1, sent_at=self.now)
        report = build_snapshot(tenant=self.tenant, now=self.now)
        self.assertNotIn('222', str(report))
        self.assertFalse(any(a['code'] == 'DELIVERY_CONFIRMATION_PENDING' for a in report['alerts']))
