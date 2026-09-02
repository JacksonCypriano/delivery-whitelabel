from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class InventoryMigrationTests(TransactionTestCase):
    def test_existing_stock_and_historical_orders_are_preserved(self):
        before = [('stores', '0009_delete_deliveryzone'), ('orders', '0009_cart_checkout_token_cart_unique_cart_tenant_user_and_more')]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            tenant = apps.get_model('tenants', 'Tenant').objects.create(name='Migration', slug='inventory-migration', whatsapp_number='5511999998811')
            category = apps.get_model('stores', 'Category').objects.create(tenant_id=tenant.pk, name='Catálogo', slug='catalogo')
            Product = apps.get_model('stores', 'Product')
            managed = Product.objects.create(tenant_id=tenant.pk, category_id=category.pk, name='Estoque', slug='estoque', price=20, stock=7)
            unlimited = Product.objects.create(tenant_id=tenant.pk, category_id=category.pk, name='Sem controle', slug='sem-controle', price=20, stock=None)
            order = apps.get_model('orders', 'Order').objects.create(tenant_id=tenant.pk, total=20, customer_phone='11999998811')
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            Product = apps.get_model('stores', 'Product')
            self.assertEqual(Product.objects.get(pk=managed.pk).stock, Decimal('7.00'))
            self.assertIsNone(Product.objects.get(pk=unlimited.pk).stock)
            self.assertEqual(apps.get_model('orders', 'Order').objects.get(pk=order.pk).total, 20)
            self.assertFalse(apps.get_model('orders', 'StockReservation').objects.exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
