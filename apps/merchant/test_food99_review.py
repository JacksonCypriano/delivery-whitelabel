"""Security and serialization regression for the read-only 99Food review API."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.merchant.food99_review import _order_public, Food99ReviewList, Food99ReviewDetail


class Food99ReviewTests(SimpleTestCase):
    def setUp(self):
        self.tenant = SimpleNamespace(id=5, slug='vitrine-demo')
        self.user = Mock(is_authenticated=True, is_active=True, must_change_password=False)
        self.user.is_staff = True
        self.factory = APIRequestFactory()

    def _request(self, route):
        req = self.factory.get(route)
        req.tenant = self.tenant
        force_authenticate(req, user=self.user)
        return req

    def test_public_fields_exclude_sensitive_data(self):
        row = SimpleNamespace(
            pk=17, external_id='order17', state='changed', last_seen_status=922,
            item_count=3, amount_minor=1399, change_count=1, revision_count=2,
            app_shop_id='vdd-vitrine-demo', updated_at=datetime.now(timezone.utc),
            connection=SimpleNamespace(merchant_id='shop17'),
            encrypted_snapshot='SHOULD_NOT_APPEAR',
            latest_encrypted_snapshot='ALSO_SECRET',
        )
        payload = _order_public(row)
        self.assertNotIn('encrypted_snapshot', payload)
        self.assertNotIn('latest_encrypted_snapshot', payload)
        self.assertNotIn('token', payload)
        self.assertEqual(payload['status_code'], 922)
        self.assertEqual(payload['revision_count'], 2)

    @patch('apps.merchant.food99_review.Food99StagedOrder.objects')
    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    def test_list_is_scoped_to_authenticated_tenant(self, _allowed, objects):
        queryset = MagicMock()
        objects.filter.return_value = queryset
        queryset.select_related.return_value = queryset
        queryset.annotate.return_value = queryset
        queryset.order_by.return_value = queryset
        queryset.count.return_value = 0
        queryset.__getitem__ = Mock(return_value=[])
        response = Food99ReviewList.as_view()(self._request('/review/'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['operational_enabled'])
        self.assertEqual(objects.filter.call_args.kwargs['connection__tenant'], self.tenant)
        self.assertEqual(objects.filter.call_args.kwargs['connection__mode'], 'test')

    @patch('apps.merchant.food99_review.Food99StagedOrder.objects')
    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    def test_detail_does_not_expose_foreign_tenant_order(self, _allowed, objects):
        queryset = MagicMock()
        objects.filter.return_value = queryset
        queryset.select_related.return_value = queryset
        queryset.annotate.return_value = queryset
        queryset.first.return_value = None
        response = Food99ReviewDetail.as_view()(self._request('/review/25/'), pk=25)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(objects.filter.call_args.kwargs['connection__tenant'], self.tenant)

    @patch('apps.merchant.api.tenant_admin_allowed', return_value=True)
    def test_invalid_page_rejected(self, _allowed):
        response = Food99ReviewList.as_view()(self._request('/review/?page=abc'))
        self.assertEqual(response.status_code, 400)
