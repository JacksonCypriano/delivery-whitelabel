"""P28: safe backlog selection, tenant isolation, and replay semantics."""
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.channels.connectors import ProviderError
from apps.channels.food99_backlog import plan_backlog, run_backlog
from apps.channels.models import Connection, ExternalOrder, Inbox, Outbox
from apps.orders.models import Order
from apps.tenants.models import Tenant

HML = dict(SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
           CHANNELS_LIVE_ENABLED=False, CHANNELS_NETWORK_ENABLED=False,
           FOOD99_SANDBOX_IMPORT_TO_ORDERS=True, FOOD99_LOCAL_EVENT_SYNC_ENABLED=True)


@override_settings(**HML)
class Food99BacklogTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Backlog A', slug='backlog-a', whatsapp_number='5511999994401')
        self.other = Tenant.objects.create(name='Backlog B', slug='backlog-b', whatsapp_number='5511999994402')
        self.conn = Connection.objects.create(tenant=self.tenant, provider='99food', mode='test',
                                              enabled=False, merchant_id='p28-1')
        self.other_conn = Connection.objects.create(tenant=self.other, provider='99food', mode='test',
                                                    enabled=False, merchant_id='p28-2')
        self.order = Order.objects.create(tenant=self.tenant, source='99food', status='pending',
                                          customer_name='Fixture', total='10', subtotal='10',
                                          delivery_type='delivery', payment_flow='marketplace',
                                          payment_method='online')
        self.external = ExternalOrder.objects.create(connection=self.conn, order=self.order,
                                                     external_id='123456', encrypted_snapshot='fixture')

    def event(self, *, code='orderConfirm', conn=None, order_id='123456', valid=True):
        conn = conn or self.conn
        digest = '%064x' % (Inbox.objects.count() + 1)
        return Inbox.objects.create(connection=conn, external_id='99food-' + digest,
            order_id=order_id, code=code, state='blocked', occurred_at=timezone.now(),
            payload={'food99_quarantined': True, 'operational_enabled': False,
                     'app_shop_id': 'vdd-' + conn.tenant.slug if valid else 'vdd-wrong',
                     'raw_sha256': digest})

    def test_preview_only_imported_and_supported(self):
        self.event(code='orderNew')
        self.event(order_id='99999')
        valid = self.event()
        with patch('requests.post') as post, patch('requests.get') as get:
            report = plan_backlog(tenant_slug=self.tenant.slug)
        self.assertEqual(report['selected'], 1)
        self.assertEqual(report['events'][0]['event_id'], valid.pk)
        self.assertEqual(report['ready'], 1)
        self.assertTrue(report['read_only'])
        post.assert_not_called(); get.assert_not_called()

    def test_cursor_paginates_past_invalid_envelopes(self):
        invalid = self.event(valid=False)
        good = self.event()
        first = plan_backlog(tenant_slug=self.tenant.slug, limit=1)
        self.assertEqual(first['events'][0]['result'], 'INVALID_ENVELOPE')
        self.assertTrue(first['has_more'])
        self.assertEqual(first['next_cursor'], invalid.pk)
        second = plan_backlog(tenant_slug=self.tenant.slug, limit=1, cursor=first['next_cursor'])
        self.assertEqual(second['events'][0]['event_id'], good.pk)
        self.assertFalse(second['has_more'])

    @patch('apps.channels.food99_local_sync.publish_order_event')
    def test_apply_once_only_after_signed_webhook(self, publish):
        event = self.event()
        cmd = Outbox.objects.create(external_order=self.external, target='confirmed',
                                    from_status='pending', state='awaiting', payload={})
        with patch('requests.post') as post:
            self.assertEqual(run_backlog(tenant_slug=self.tenant.slug)['updated'], 0)
            self.assertEqual(self.order.status, 'pending')
            with self.captureOnCommitCallbacks(execute=True):
                report = run_backlog(tenant_slug=self.tenant.slug, apply=True)
            again = run_backlog(tenant_slug=self.tenant.slug, apply=True)
        self.assertEqual(report['updated'], 1)
        self.assertEqual(again['updated'], 0)
        event.refresh_from_db(); self.order.refresh_from_db(); cmd.refresh_from_db()
        self.assertEqual(event.state, 'processed')
        self.assertEqual(self.order.status, 'confirmed')
        self.assertEqual(cmd.state, 'confirmed')
        publish.assert_called_once()
        post.assert_not_called()

    def test_isolation_and_invalid_arguments(self):
        self.event()
        foreign = self.event(conn=self.other_conn)
        self.assertEqual(plan_backlog(tenant_slug=self.other.slug)['selected'], 0)
        self.assertEqual(plan_backlog(tenant_slug=self.tenant.slug)['selected'], 1)
        self.assertEqual(Inbox.objects.get(pk=foreign.pk).state, 'blocked')
        for kwargs in ({'limit': 0}, {'cursor': -1}, {'limit': True}, {'cursor': '1'}):
            with self.assertRaises(ProviderError):
                plan_backlog(tenant_slug=self.tenant.slug, **kwargs)

    def test_live_is_explicitly_blocked(self):
        self.event()
        with override_settings(CHANNELS_LIVE_ENABLED=True):
            with self.assertRaises(ProviderError):
                run_backlog(tenant_slug=self.tenant.slug, apply=True)
