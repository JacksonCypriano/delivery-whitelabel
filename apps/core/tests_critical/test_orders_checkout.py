import uuid
from decimal import Decimal

from apps.orders.models import Cart, CartItem, Order, OrderItem

from .base import CriticalTestCase


class OrdersCheckoutCriticalTests(CriticalTestCase):
    def _anonymous_cart(self, tenant, session_key="critical-session"):
        return Cart.objects.create(tenant=tenant, session_key=session_key)

    def test_cart_items_remain_isolated_by_tenant(self):
        cart_a = self._anonymous_cart(self.tenant_a, "session-a")
        cart_b = self._anonymous_cart(self.tenant_b, "session-b")
        CartItem.objects.create(cart=cart_a, product=self.product_a, product_key="a", name=self.product_a.name, price=Decimal("20.00"), quantity=1)
        CartItem.objects.create(cart=cart_b, product=self.product_b, product_key="b", name=self.product_b.name, price=Decimal("30.00"), quantity=1)
        self.assertEqual(cart_a.items.count(), 1)
        self.assertEqual(cart_a.items.get().product, self.product_a)
        self.assertEqual(cart_b.items.get().product, self.product_b)

    def test_order_item_price_snapshot_survives_product_price_change(self):
        order = Order.objects.create(tenant=self.tenant_a, customer_name="Cliente", customer_phone="11999999999", subtotal=Decimal("20.00"), total=Decimal("20.00"))
        item = OrderItem.objects.create(order=order, product=self.product_a, name=self.product_a.name, price=Decimal("20.00"), quantity=2)
        self.product_a.price = Decimal("99.00")
        self.product_a.save()
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal("20.00"))
        self.assertEqual(item.get_total_price(), Decimal("40.00"))

    def test_order_additions_price_breakdown_uses_snapshot(self):
        order = Order.objects.create(tenant=self.tenant_a, customer_name="Cliente", customer_phone="11999999999", subtotal=Decimal("25.00"), total=Decimal("25.00"))
        item = OrderItem.objects.create(order=order, product=self.product_a, name=self.product_a.name, price=Decimal("25.00"), quantity=1, combination_details={"customizations": [{"name": "Bacon", "price": "5.00"}]})
        self.assertEqual(item.additions_unit_price, Decimal("5.00"))
        self.assertEqual(item.base_unit_price, Decimal("20.00"))
        self.assertTrue(item.has_additions)

    def test_checkout_rejects_invalid_session_token(self):
        response = self.client.get("/checkout/checkout/", HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.status_code, 302)  # carrinho vazio

        session = self.client.session
        if not session.session_key:
            session.save()
        cart = Cart.objects.create(tenant=self.tenant_a, session_key=session.session_key)
        CartItem.objects.create(cart=cart, product=self.product_a, product_key="checkout", name=self.product_a.name, price=Decimal("20.00"), quantity=1)

        response = self.client.get("/checkout/checkout/", HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/checkout/checkout/", {"checkout_token": str(uuid.uuid4()), "full_name": "Cliente", "phone": "11999999999", "delivery_type": "pickup", "payment_method": "pix"}, HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.filter(tenant=self.tenant_a).count(), 0)

    def test_whatsapp_url_cannot_open_order_from_other_tenant(self):
        order = Order.objects.create(tenant=self.tenant_a, customer_name="Cliente", customer_phone="11999999999", subtotal=Decimal("20.00"), total=Decimal("20.00"))
        response = self.client.get(f"/pedido/{order.public_token}/whatsapp/", HTTP_HOST=self.host(self.tenant_b))
        self.assertEqual(response.status_code, 404)
        order.refresh_from_db()
        self.assertIsNone(order.whatsapp_opened_at)
