from unittest.mock import patch, MagicMock
from django.core.management.base import CommandError
from django.test import SimpleTestCase
from apps.channels.management.commands.review_99food_sandbox_batch import parse_order_ids, compare_existing


class BatchValidationTests(SimpleTestCase):
    def test_ids(self):
        self.assertEqual(parse_order_ids('123,456'), ['123','456'])
        for raw in ('', '12,12', '3;4', 'abc', '1,', ',1', ','.join(str(i) for i in range(51))):
            with self.subTest(raw=raw), self.assertRaises(CommandError):
                parse_order_ids(raw)

    @patch('apps.channels.management.commands.review_99food_sandbox_batch.Connection.objects')
    def test_missing_connection_is_new(self, manager):
        manager.filter.return_value.first.return_value = None
        self.assertEqual(compare_existing(shop_id='1',order_id='2',tenant_id=None,fingerprint='x'),'novo')

    @patch('apps.channels.management.commands.review_99food_sandbox_batch.Connection.objects')
    def test_wrong_tenant_rejected(self, manager):
        conn=MagicMock(tenant_id=7)
        manager.filter.return_value.first.return_value=conn
        with self.assertRaises(CommandError):
            compare_existing(shop_id='1',order_id='2',tenant_id=8,fingerprint='x')

    @patch('apps.channels.management.commands.review_99food_sandbox_batch.Connection.objects')
    @patch('apps.channels.management.commands.review_99food_sandbox_batch.ExternalOrder.objects')
    def test_existing_fingerprint(self, orders, connections):
        connection=MagicMock(tenant_id=7)
        connections.filter.return_value.first.return_value=connection
        existing=MagicMock()
        existing.order.tenant_id=7
        existing.order.source='99food'
        existing.financials={'snapshot_fingerprint':'abc'}
        orders.filter.return_value.select_related.return_value.first.return_value=existing
        self.assertEqual(compare_existing(shop_id='1',order_id='2',tenant_id=7,fingerprint='abc'),'igual')
        self.assertEqual(compare_existing(shop_id='1',order_id='2',tenant_id=7,fingerprint='xyz'),'divergente')
