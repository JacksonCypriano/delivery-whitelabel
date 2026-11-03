"""Package 14: dry-run and event preflight regressions, no DB required."""
import json
from unittest.mock import MagicMock, Mock, patch
from types import SimpleNamespace
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.channels.food99_operational_dryrun import format_dry_run
from apps.channels.food99_event_preflight import inspect_untrusted_event
from apps.merchant.food99_operational_api import Food99OperationalDryRun


class Package14Tests(SimpleTestCase):
    def setUp(self):
        self.data = dict(external_id='123', state='reviewed', status_code=922,
                         items=[dict(name='Pizza', quantity=2, line_total_minor=2000,
                                     options=[dict(name='Borda', price='2.00')])],
                         total_minor=2100, delivery_by='MERCHANT',
                         payment_method='cash')

    def test_dryrun_never_creates_order_or_unblocks_kds(self):
        result = format_dry_run(self.data)
        self.assertFalse(result['operational_enabled'])
        self.assertFalse(result['kds_visible'])
        self.assertEqual(result['orders_created'], 0)
        self.assertEqual(result['allowed_transitions'], [])
        self.assertEqual(len(result['contract_gates']), 6)
        self.assertTrue(all(not v['approved'] for v in result['contract_gates']))
        self.assertEqual(result['quantity_total'], 2)

    def test_dryrun_financial_difference_is_informational(self):
        result = format_dry_run(self.data)
        self.assertIn('TOTAL_NOT_EQUAL_LINES', [d['code'] for d in result['diagnostics']])
        self.assertFalse(result['payment_confirmed'])
        self.assertFalse(result['currency_confirmed'])

    def test_dryrun_does_not_leak_customer_fields(self):
        data = dict(self.data, customer='CUSTOMER_SECRET', phone='SECRET_PHONE')
        result = format_dry_run(data)
        self.assertNotIn('CUSTOMER_SECRET', str(result))
        self.assertNotIn('SECRET_PHONE', str(result))

    def test_untrusted_webhook_never_acknowledged_even_with_claimed_flags(self):
        raw = json.dumps({'customer': 'PRIVATE', 'event': 'abc'}).encode()
        result = inspect_untrusted_event(raw, authenticated=True, contract_approved=True)
        self.assertFalse(result['accepted'])
        self.assertFalse(result['acknowledged'])
        self.assertNotIn('PRIVATE', str(result))

    def test_untrusted_callback_rejects_large_payload(self):
        result = inspect_untrusted_event(b'a' * 131073)
        self.assertEqual(result, {'accepted': False, 'reason': 'BODY_TOO_LARGE'})

    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    @patch('apps.merchant.food99_operational_api.dry_run_staged', create=True)
    @patch('apps.merchant.food99_operational_api.Food99StagedOrder.objects')
    def test_foreign_tenant_dryrun_is_404_before_preview(self, objects, _dryrun, _allowed):
        objects.select_related.return_value.filter.return_value.first.return_value=None
        req=APIRequestFactory().get('/test/')
        tenant=SimpleNamespace(pk=42,slug='other')
        req.tenant=tenant
        force_authenticate(req,user=Mock(is_authenticated=True,is_active=True,must_change_password=False,is_staff=True))
        res=Food99OperationalDryRun.as_view()(req,pk=123)
        self.assertEqual(res.status_code,404)
        self.assertEqual(objects.select_related.return_value.filter.call_args.kwargs['connection__tenant'],tenant)

    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    @patch('apps.merchant.food99_operational_api.Food99StagedOrder.objects')
    def test_batch_dryrun_prevents_cross_tenant_leakage(self, objects, _allowed):
        from apps.merchant.food99_operational_api import Food99OperationalBatchDryRun
        objects.select_related.return_value.filter.return_value = []
        req=APIRequestFactory().post('/dryrun-batch/', {'ids':[2]}, format='json')
        tenant=SimpleNamespace(pk=99,slug='foreign')
        req.tenant=tenant
        force_authenticate(req,user=Mock(is_authenticated=True,is_active=True,must_change_password=False,is_staff=True))
        res=Food99OperationalBatchDryRun.as_view()(req)
        self.assertEqual(res.status_code,404)
        self.assertEqual(objects.select_related.return_value.filter.call_args.kwargs['connection__tenant'],tenant)

    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    def test_batch_dryrun_rejects_repeated_ids_without_db(self, _allowed):
        from apps.merchant.food99_operational_api import Food99OperationalBatchDryRun
        req=APIRequestFactory().post('/dryrun-batch/', {'ids':[1,1]}, format='json')
        req.tenant=SimpleNamespace(pk=99,slug='foreign')
        force_authenticate(req,user=Mock(is_authenticated=True,is_active=True,must_change_password=False,is_staff=True))
        res=Food99OperationalBatchDryRun.as_view()(req)
        self.assertEqual(res.status_code,400)
