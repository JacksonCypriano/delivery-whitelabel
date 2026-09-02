from decimal import Decimal
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class Package10MigrationTests(TransactionTestCase):
    def test_existing_carts_are_repaired_without_changing_historical_orders(self):
        before = [("orders", "0008_alter_order_public_token")]
        after = [
            ("orders", "0009_cart_checkout_token_cart_unique_cart_tenant_user_and_more")
        ]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            Tenant = apps.get_model("tenants", "Tenant")
            Cart = apps.get_model("orders", "Cart")
            Item = apps.get_model("orders", "CartItem")
            Order = apps.get_model("orders", "Order")
            from apps.tenants.models import Tenant as CurrentTenant

            tenant = CurrentTenant.objects.create(
                name="Migration", slug="migration", whatsapp_number="5511999998888"
            )
            a = Cart.objects.create(tenant_id=tenant.pk, session_key="same")
            b = Cart.objects.create(tenant_id=tenant.pk, session_key="same")
            c = Cart.objects.create(tenant_id=tenant.pk, session_key="other")
            Item.objects.create(
                cart=a, product_key="same", name="A", price=10, quantity=1
            )
            Item.objects.create(
                cart=b, product_key="same", name="B", price=20, quantity=2
            )
            Item.objects.create(
                cart=c, product_key="zero", name="Zero", price=10, quantity=0
            )
            Item.objects.create(
                cart=c, product_key="negative", name="Negative", price=-10, quantity=1
            )
            order = Order.objects.create(
                tenant_id=tenant.pk, customer_phone="11999999999", subtotal=30, total=30
            )
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            carts = apps.get_model("orders", "Cart").objects.all()
            self.assertEqual(carts.count(), 2)
            self.assertEqual(
                len(set(carts.values_list("checkout_token", flat=True))), 2
            )
            items = apps.get_model("orders", "CartItem").objects.all()
            self.assertEqual(items.count(), 2)
            self.assertEqual(
                sum(item.price * item.quantity for item in items), Decimal("50")
            )
            self.assertEqual(
                apps.get_model("orders", "Order").objects.get(pk=order.pk).total,
                Decimal("30"),
            )
        finally:
            # Restore current schema even if an assertion or migration fails.
            MigrationExecutor(connection).migrate(latest)
