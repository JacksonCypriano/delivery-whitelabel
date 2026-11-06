"""Manual batch reconciliation must be bounded, scoped and read-only by default."""
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch
from django.test import TestCase, override_settings
from apps.tenants.models import Tenant
from apps.channels.models import Connection, Inbox
from apps.channels.connectors import ProviderError
from apps.channels.food99_webhook_batch import reconcile_batch


@override_settings(SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
                   CHANNELS_NETWORK_ENABLED=False, CHANNELS_LIVE_ENABLED=False)
class Food99BatchTests(TestCase):
    def setUp(self):
        self.t = Tenant.objects.create(name='Batch', slug='batch', whatsapp_number='5511999990000')
        self.c = Connection.objects.create(tenant=self.t, provider='99food', mode='test',
                                           merchant_id='111', enabled=False)
        for n in range(3):
            Inbox.objects.create(connection=self.c, external_id='99food-'+str(n)*64,
                 code='orderNew', order_id=str(n+100), state='blocked',
                 occurred_at=datetime(2026, 11, 4, tzinfo=dt_timezone.utc),
                 payload={'food99_quarantined': True, 'operational_enabled': False,
                          'app_shop_id':'vdd-batch', 'raw_sha256':str(n)*64})

    def test_scoped_bounded_preview(self):
        with patch('apps.channels.food99_webhook_batch.reconcile',
                   side_effect=lambda pk, apply: {'state':'QUARANTINED'}) as fn:
            result = reconcile_batch(tenant_slug='batch',limit=2)
        self.assertEqual(result['selected'], 2)
        self.assertEqual(result['ok'], 2)
        self.assertEqual(fn.call_count, 2)
        self.assertTrue(all(call.kwargs['apply'] is False for call in fn.call_args_list))

    def test_other_tenant_unavailable(self):
        self.assertEqual(reconcile_batch(tenant_slug='other')['selected'], 0)

    def test_bounds_and_isolation(self):
        for limit in (0, 101, True, -1):
            with self.assertRaises(ProviderError):
                reconcile_batch(tenant_slug='batch',limit=limit)
        with override_settings(SETTINGS_MODULE='config.settings.prod'):
            with self.assertRaises(ProviderError):reconcile_batch(tenant_slug='batch')

    def test_failure_does_not_silently_acknowledge(self):
        with patch('apps.channels.food99_webhook_batch.reconcile',
                   side_effect=ProviderError('private')):
            result = reconcile_batch(tenant_slug='batch', limit=2, apply=True)
        self.assertEqual(result['failed'], 2)
        self.assertEqual(Inbox.objects.filter(state='blocked').count(), 3)
