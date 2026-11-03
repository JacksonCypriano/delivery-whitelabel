"""99Food Package 13: negative-path and privacy regression tests."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.channels.connectors import ProviderError
from apps.channels.food99_operational_preview import readiness, _safe_order, preview_staged
from apps.channels.food99_sandbox_batch import stage_by_id, refresh_batch
from apps.channels.food99_integrity import audit_row, audit_summary
from apps.merchant.food99_operational_api import (
    Food99OperationalReadiness, Food99OperationalPreview,
    Food99SandboxStage, Food99SandboxBatchRefresh,
)


class Food99OperationalPreflightTests(SimpleTestCase):
    def setUp(self):
        self.tenant = SimpleNamespace(pk=7, slug='vitrine-demo')
        self.factory = APIRequestFactory()
        self.user = Mock(is_authenticated=True, is_active=True,
                         must_change_password=False, is_staff=True)

    def _request(self, path, data=None):
        request = (self.factory.get(path) if data is None else
                   self.factory.post(path, data, format='json'))
        request.tenant = self.tenant
        force_authenticate(request, user=self.user)
        return request

    def test_integrity_audit_does_not_decrypt_or_expose_snapshot(self):
        row = SimpleNamespace(
            pk=15, state='reviewed', fingerprint='x'*64, latest_fingerprint='x'*64,
            encrypted_snapshot='SECRET_ENCRYPTED', latest_encrypted_snapshot='MORE_SECRET',
            item_count=3, amount_minor=18500, revision_count=2,
            connection=SimpleNamespace(provider='99food', mode='test', enabled=False),
        )
        self.assertEqual(audit_row(row, revision_count=2), [])
        result = audit_summary([row], total=1, limit=100)
        self.assertEqual(result['affected_scanned'], 0)
        self.assertNotIn('SECRET_', str(result))
        self.assertFalse(result['operational_enabled'])

    def test_integrity_flags_missing_revision_but_never_mutates_row(self):
        row = SimpleNamespace(
            pk=2, state='review', fingerprint='x'*64, latest_fingerprint='',
            encrypted_snapshot='abc', latest_encrypted_snapshot='',
            item_count=1, amount_minor=100, revision_count=0,
            connection=SimpleNamespace(provider='99food', mode='test', enabled=False),
        )
        flags = audit_row(row, revision_count=0)
        self.assertIn('NO_REVISIONS', flags)
        self.assertIn('MISSING_LATEST_SNAPSHOT', flags)

    def test_readiness_never_unlocks_unknown_status(self):
        result = readiness(sandbox_enabled=True,
            connection=SimpleNamespace(enabled=False), staged_count=1,
            reviewed_count=1, statuses=[922, 923, 922])
        self.assertFalse(result['operational_enabled'])
        self.assertFalse(result['can_promote_orders'])
        self.assertFalse(result['can_send_transitions'])
        self.assertFalse(result['can_receive_webhooks'])
        self.assertEqual(len([b for b in result['blockers'] if b['code']=='unmapped_status']), 2)

    def test_preview_never_exposes_customer_or_transitions(self):
        payload = {
            'status_code':922, 'items':[{
                'name':'Pizza', 'quantity':2, 'line_total':Decimal('20.00'),
                'notes':'Phone 111111', 'options':[{'option_name':'Borda', 'price':'2.00'}]}],
            'total':Decimal('20.00'), 'delivery_by':'MERCHANT',
            'payment_method':'cash', 'paid':False,
            'customer':'CUSTOMER_SECRET',
        }
        data = _safe_order(payload, state='reviewed', external_id='999')
        self.assertNotIn('CUSTOMER_SECRET', str(data))
        self.assertNotIn('Phone 111111', str(data))
        self.assertEqual(data['allowed_transitions'], [])
        self.assertFalse(data['operational_enabled'])
        self.assertFalse(data['kds_visible'])

    def test_preview_rejects_non_test_provider(self):
        row = SimpleNamespace(connection=SimpleNamespace(provider='ifood', mode='test'))
        with self.assertRaises(ProviderError):
            preview_staged(row)

    @patch('apps.channels.food99_sandbox_batch.get_order_detail')
    def test_invalid_order_id_never_calls_remote_api(self, remote):
        with self.assertRaises(ProviderError):
            stage_by_id(tenant=self.tenant, order_id='../other-tenant')
        remote.assert_not_called()

    @override_settings(FOOD99_SANDBOX_ENABLED=True)
    @patch('apps.channels.food99_sandbox_batch.get_order_detail')
    @patch('apps.channels.food99_sandbox_batch.Connection.objects')
    def test_stage_rejects_unlinked_store_before_remote_call(self, qs, remote):
        qs.filter.return_value.exclude.return_value.order_by.return_value.__getitem__.return_value = []
        with self.assertRaises(ProviderError):
            stage_by_id(tenant=self.tenant, order_id='123456')
        remote.assert_not_called()
        self.assertEqual(qs.filter.call_args.kwargs['tenant'], self.tenant)

    def test_batch_rejects_duplicates_and_too_many(self):
        for ids in ([1,1], [1,2,3,4,5,6], ['1'], [], [True]):
            with self.subTest(ids=ids), self.assertRaises(ProviderError):
                refresh_batch(tenant=self.tenant, ids=ids)

    @patch('apps.channels.food99_sandbox_batch.Food99StagedOrder.objects')
    @patch('apps.channels.food99_sandbox_batch.refresh_staged_order')
    def test_batch_rejects_foreign_rows_before_remote_call(self, refresh, objects):
        objects.filter.return_value = []
        with self.assertRaises(ProviderError):
            refresh_batch(tenant=self.tenant, ids=[7])
        refresh.assert_not_called()
        self.assertEqual(objects.filter.call_args.kwargs['connection__tenant'], self.tenant)

    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    @patch('apps.merchant.food99_operational_api.Food99StagedOrder.objects')
    def test_operational_preview_404_for_foreign_tenant(self, objects, _allowed):
        objects.select_related.return_value.filter.return_value.first.return_value = None
        response=Food99OperationalPreview.as_view()(self._request('/preview/9/'), pk=9)
        self.assertEqual(response.status_code,404)
        self.assertEqual(objects.select_related.return_value.filter.call_args.kwargs['connection__tenant'],self.tenant)

    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    @patch('apps.merchant.food99_operational_api.stage_by_id')
    def test_stage_endpoint_rejects_non_numeric_order_id(self, staged, _allowed):
        response=Food99SandboxStage.as_view()(self._request('/stage/', {'order_id':1234}))
        self.assertEqual(response.status_code,400)
        staged.assert_not_called()

    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    @patch('apps.merchant.food99_operational_api.refresh_batch')
    def test_batch_endpoint_returns_non_operational_flags(self, batch, _allowed):
        batch.return_value = [{'id':1,'result':'UNCHANGED'}]
        response=Food99SandboxBatchRefresh.as_view()(self._request('/batch/', {'ids':[1]}))
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.data['operational_enabled'])
        self.assertFalse(response.data['kds_visible'])
