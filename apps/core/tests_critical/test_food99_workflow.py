"""Security/contract tests for the extended 99Food sandbox review workflow."""
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.channels.food99_review_workflow import status_policy
from apps.merchant.food99_workflow_api import (
    Food99ReviewAcknowledge, Food99ReviewCompare, Food99ReviewRefresh, Food99ReviewSummary,
)


class Food99SandboxWorkflowTests(SimpleTestCase):
    def setUp(self):
        self.tenant = SimpleNamespace(pk=4, slug='vitrine-demo')
        self.user = Mock(is_authenticated=True, is_active=True, must_change_password=False)
        self.factory = APIRequestFactory()

    def _get(self, url):
        request = self.factory.get(url)
        request.tenant = self.tenant
        force_authenticate(request, user=self.user)
        return request

    def _post(self, url, data=None):
        request = self.factory.post(url, data or {}, format='json')
        request.tenant = self.tenant
        force_authenticate(request, user=self.user)
        return request

    def test_unknown_status_never_maps_to_kds(self):
        for status in [922, 0, 1, 1000, -1]:
            policy = status_policy(status)
            self.assertFalse(policy['mapped'])
            self.assertIsNone(policy['operational_status'])

    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    @patch('apps.merchant.food99_workflow_api.Food99StagedOrder.objects')
    def test_refresh_does_not_expose_other_tenant(self, objects, _allowed):
        objects.select_related.return_value.filter.return_value.first.return_value = None
        response = Food99ReviewRefresh.as_view()(self._post('/refresh/'), pk=51)
        self.assertEqual(response.status_code, 403 if response.status_code == 403 else 404)
        if response.status_code == 404:
            self.assertEqual(objects.select_related.return_value.filter.call_args.kwargs['connection__tenant'], self.tenant)

    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    @patch('apps.merchant.food99_workflow_api.Food99StagedOrder.objects')
    def test_review_get_exposes_only_fingerprint_and_gate(self, objects, _allowed):
        objects.select_related.return_value.filter.return_value.first.return_value = SimpleNamespace(
            fingerprint='a'*64, latest_fingerprint='b'*64, state='changed', last_seen_status=922)
        response = Food99ReviewAcknowledge.as_view()(self._get('/review/20/'), pk=20)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['operational_enabled'])
        self.assertFalse(response.data['status_policy']['mapped'])
        self.assertNotIn('snapshot', str(response.data))

    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    @patch('apps.merchant.food99_workflow_api.Food99StagedOrder.objects')
    def test_compare_rejects_invalid_versions(self, objects, _allowed):
        objects.select_related.return_value.filter.return_value.first.return_value = SimpleNamespace(pk=20)
        response = Food99ReviewCompare.as_view()(self._get('/compare/?from=2&to=1'), pk=20)
        self.assertEqual(response.status_code, 400)

    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    @patch('apps.merchant.food99_workflow_api.Food99StagedOrder.objects')
    def test_summary_does_not_list_order_ids(self, objects, _allowed):
        qs = MagicMock()
        objects.filter.return_value = qs
        qs.values.return_value.annotate.return_value = [{'state': 'changed', 'total': 1}]
        response = Food99ReviewSummary.as_view()(self._get('/summary/'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['by_state']['changed'], 1)
        self.assertNotIn('external_id', response.data)
        self.assertFalse(response.data['operational_enabled'])

class Food99PolicyRegressionTests(SimpleTestCase):
    @patch('apps.channels.food99_review_workflow.Food99StagedOrder.objects')
    @patch('apps.channels.food99_review_workflow.get_order_detail')
    def test_refresh_never_calls_provider_for_foreign_tenant(self, remote, objects):
        from apps.channels.food99_review_workflow import refresh_staged_order
        from apps.channels.connectors import ProviderError
        objects.select_related.return_value.filter.return_value.first.return_value = None
        with self.assertRaises(ProviderError):
            refresh_staged_order(tenant=SimpleNamespace(pk=77), pk=900)
        remote.assert_not_called()

    @patch('apps.channels.food99_review_compare._read')
    def test_revision_comparison_does_not_expose_customer_fields(self, read):
        from decimal import Decimal
        from apps.channels.food99_review_compare import compare_revisions
        before = {'status_code': 922, 'total': Decimal('10.00'),
                  'real_pay': Decimal('10.00'), 'delivery_fee': Decimal('0'),
                  'discount': Decimal('0'), 'items': [
                      {'code': 'sku', 'name': 'Pizza', 'quantity': 1,
                       'line_total': Decimal('10.00'), 'options': []}],
                  'customer': 'NEVER_EXPOSE'}
        after = {**before, 'total': Decimal('12.00'), 'status_code': 923}
        read.side_effect = [before, after]
        row = SimpleNamespace(pk=100)
        one = SimpleNamespace(version=1, staged_order_id=100)
        two = SimpleNamespace(version=2, staged_order_id=100)
        changes = compare_revisions(row, one, two)
        self.assertTrue(changes['status_changed'])
        self.assertEqual(changes['money_changes'][0]['after_minor'], 1200)
        self.assertNotIn('NEVER_EXPOSE', str(changes))
        self.assertFalse(changes['operational_enabled'])
