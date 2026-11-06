from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from apps.channels.connectors import ProviderError
from apps.channels.food99_staging import stage_order


class StageGuardTests(TestCase):
    def setUp(self):
        self.tenant = MagicMock(pk=8, slug='vitrine-demo')

    @override_settings(FOOD99_SANDBOX_ENABLED=False)
    def test_disabled_sandbox_rejects(self):
        with self.assertRaises(ProviderError):
            stage_order({}, tenant=self.tenant, app_shop_id='vdd-vitrine-demo',
                        shop_id='123', order_id='456')

    @override_settings(FOOD99_SANDBOX_ENABLED=True)
    def test_wrong_tenant_rejects(self):
        with self.assertRaises(ProviderError):
            stage_order({}, tenant=self.tenant, app_shop_id='vdd-other',
                        shop_id='123', order_id='456')
