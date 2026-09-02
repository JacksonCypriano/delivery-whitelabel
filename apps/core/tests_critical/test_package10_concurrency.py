"""PostgreSQL gates: requests use separate DB connections and start together."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.db import close_old_connections, connections, transaction
from django.test import RequestFactory, TransactionTestCase, skipUnlessDBFeature

from apps.checkout.views import add_to_cart, checkout_step_one
from apps.orders.views import open_whatsapp
from apps.orders.models import Cart, CartItem, Order
from apps.orders import cart_service as integrity
from apps.stores.models import Category, Product
from apps.tenants.models import Tenant
from apps.tenants.choices import FulfillmentMode
from apps.customers.models import Customer
from apps.coupons.models import CouponCampaign


@skipUnlessDBFeature("has_select_for_update")
class Package10ConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja",
            slug="concurrent",
            whatsapp_number="5511999998888",
            fulfillment_mode=FulfillmentMode.DELIVERY_AND_PICKUP,
            pickup_address="Rua Teste",
            pickup_number="10",
            pickup_city="São Paulo",
        )
        category = Category.objects.create(tenant=self.tenant, name="Produtos")
        self.product = Product.objects.create(
            tenant=self.tenant, category=category, name="Produto", price=Decimal("20")
        )
        self.users = []
        for i in range(2):
            user = get_user_model().objects.create_user(
                username=f"parallel{i}",
                email=f"parallel{i}@example.com",
                password="Testing123!",
            )
            Customer.objects.create(user=user, phone=f"551199999888{i}")
            self.users.append(user)

    def request(self, user, data=None):
        req = RequestFactory().post(
            "/checkout/checkout/", data or {}, HTTP_HOST="concurrent.lvh.me"
        )
        req.user = user
        req.tenant = self.tenant
        req.session = SessionStore()
        req.session.create()
        req._messages = FallbackStorage(req)
        return req

    def run_parallel(self, calls):
        barrier = Barrier(len(calls))

        def run(call):
            close_old_connections()
            try:
                # Fail promptly on a lock-order regression instead of hanging tests.
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '8s'")
                barrier.wait(timeout=10)
                return call()
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            return list(pool.map(run, calls))

    def add_request(self, user):
        req = RequestFactory().post(
            "/checkout/add/",
            json.dumps({"product_id": self.product.pk, "quantity": 1}),
            content_type="application/json",
            HTTP_HOST="concurrent.lvh.me",
        )
        req.user = user
        req.tenant = self.tenant
        req.session = SessionStore()
        req.session.create()
        req._messages = FallbackStorage(req)
        return add_to_cart(req).status_code

    def seed(self, user):
        req = self.request(user)
        with transaction.atomic():
            cart = integrity.get_cart(req)
            integrity.add_item(
                cart, integrity.quote(self.tenant, {"product_id": self.product.pk}), 1
            )
        return cart

    def submit(self, user, cart, code=""):
        req = self.request(
            user,
            {
                "checkout_token": str(cart.checkout_token),
                "full_name": "Cliente",
                "phone": "11999999999",
                "delivery_type": "pickup",
                "payment_method": "pix",
                "coupon_code": code,
            },
        )
        return checkout_step_one(req).status_code

    def test_simultaneous_first_add_has_one_cart_and_no_lost_quantity(self):
        codes = self.run_parallel(
            [
                lambda: self.add_request(self.users[0]),
                lambda: self.add_request(self.users[0]),
            ]
        )
        self.assertEqual(codes, [200, 200])
        self.assertEqual(Cart.objects.count(), 1)
        self.assertEqual(CartItem.objects.get().quantity, 2)

    def test_double_checkout_creates_one_order(self):
        cart = self.seed(self.users[0])
        codes = self.run_parallel(
            [
                lambda: self.submit(self.users[0], cart),
                lambda: self.submit(self.users[0], cart),
            ]
        )
        self.assertEqual(codes, [200, 200])
        self.assertEqual(Order.objects.count(), 1)

    def test_last_coupon_use_reserved_once(self):
        campaign = CouponCampaign.objects.create(
            tenant=self.tenant,
            name="Último",
            code="ULTIMO",
            discount_type="fixed_amount",
            discount_value=2,
            usage_limit=1,
        )
        carts = [self.seed(u) for u in self.users]
        codes = self.run_parallel(
            [
                lambda: self.submit(self.users[0], carts[0], "ULTIMO"),
                lambda: self.submit(self.users[1], carts[1], "ULTIMO"),
            ]
        )
        self.assertEqual(sorted(codes), [200, 400])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(campaign.redemptions.count(), 1)

    def test_double_whatsapp_open_is_idempotent(self):
        user = self.users[0]
        cart = self.seed(user)
        self.submit(user, cart)
        order = Order.objects.get()

        def send():
            req = self.request(user)
            return open_whatsapp(req, order.public_token).status_code

        self.assertEqual(self.run_parallel([send, send]), [302, 302])
        order.refresh_from_db()
        self.assertIsNotNone(order.whatsapp_opened_at)
        self.assertEqual(Cart.objects.count(), 1)
        self.assertFalse(CartItem.objects.exists())
