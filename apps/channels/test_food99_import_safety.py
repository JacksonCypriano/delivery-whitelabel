from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase, override_settings
from apps.channels.connectors import ProviderError
from apps.channels.food99_import import import_reviewed


class ImportSafetyTests(TestCase):
    @override_settings(FOOD99_SANDBOX_ENABLED=False)
    def test_disabled_sandbox_never_writes(self):
        with self.assertRaises(ProviderError):
            import_reviewed({}, tenant_id=1, app_shop_id='vdd-vitrine-demo', shop_id='123', order_id='456', currency='BRL', status_override='pending')

    @override_settings(FOOD99_SANDBOX_ENABLED=True)
    @patch('apps.channels.food99_import.preview', return_value={'order_id':'456'})
    @patch('apps.tenants.models.Tenant.objects.filter')
    def test_cross_tenant_appshopid_rejected(self, tenant_filter, _preview):
        tenant_filter.return_value.first.return_value=SimpleNamespace(pk=1,slug='outra-loja')
        with self.assertRaisesMessage(ProviderError, 'AppShopID'):
            import_reviewed({}, tenant_id=1, app_shop_id='vdd-vitrine-demo', shop_id='123', order_id='456', currency='BRL', status_override='pending')

    @override_settings(FOOD99_SANDBOX_ENABLED=True, FOOD99_SANDBOX_IMPORT_TO_ORDERS=False)
    @patch('apps.channels.food99_import.preview', return_value={'order_id':'456'})
    @patch('apps.tenants.models.Tenant.objects.filter')
    def test_unreviewed_pending_orders_cannot_enter_board(self, tenant_filter, _preview):
        tenant_filter.return_value.first.return_value=SimpleNamespace(pk=1,slug='vitrine-demo')
        with self.assertRaisesMessage(ProviderError, 'desabilitada'):
            import_reviewed({}, tenant_id=1, app_shop_id='vdd-vitrine-demo', shop_id='123', order_id='456', currency='BRL', status_override='pending')
