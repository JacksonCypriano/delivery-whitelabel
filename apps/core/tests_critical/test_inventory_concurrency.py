"""PostgreSQL regression gates: separate connections and simultaneous requests."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.db import close_old_connections, connections, transaction
from django.test import RequestFactory, TransactionTestCase, skipUnlessDBFeature

from apps.checkout.views import checkout_step_one
from apps.orders.views import open_whatsapp
from apps.orders import cart_service as integrity
from apps.orders.inventory import cancel, active_reservations
from apps.orders.models import Cart, Order, StockReservation
from apps.stores.models import Category, Product
from apps.tenants.models import Tenant


@skipUnlessDBFeature('has_select_for_update')
class InventoryConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Concorrência', slug='stock', whatsapp_number='5511999998877', pickup_address='Rua', pickup_number='1')
        category = Category.objects.create(tenant=self.tenant, name='Catálogo')
        self.product = Product.objects.create(tenant=self.tenant, category=category, name='Última unidade', price=20, stock=1)
        self.users = [get_user_model().objects.create_user(username=f'stock{i}') for i in range(2)]
        self.carts = []
        for user in self.users:
            cart = Cart.objects.create(tenant=self.tenant, user=user)
            with transaction.atomic():
                integrity.add_item(cart, integrity.quote(self.tenant, {'product_id': self.product.pk}), 1)
            self.carts.append(cart)

    def request(self, user, cart):
        request = RequestFactory().post('/checkout/checkout/', {'checkout_token': str(cart.checkout_token), 'full_name': 'Cliente', 'phone': '11988887777', 'delivery_type': 'pickup', 'payment_method': 'pix'})
        request.user = user
        request.tenant = self.tenant
        request.session = SessionStore()
        request.session.create()
        request._messages = FallbackStorage(request)
        return request

    def parallel(self, calls):
        barrier = Barrier(len(calls))
        def run(call):
            close_old_connections()
            try:
                with connections['default'].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '8s'")
                barrier.wait(timeout=10)
                return call()
            finally:
                connections['default'].close()
        with ThreadPoolExecutor(max_workers=len(calls)) as executor:
            return list(executor.map(run, calls))

    def submit(self, index):
        return checkout_step_one(self.request(self.users[index], self.carts[index])).status_code

    def send(self, order):
        return open_whatsapp(self.request(self.users[0], self.carts[0]), order.public_token).status_code

    def test_last_unit_reserved_by_only_one_checkout(self):
        statuses = self.parallel([lambda: self.submit(0), lambda: self.submit(1)])
        self.assertEqual(sorted(statuses), [200, 302])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(active_reservations().count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)

    def test_double_send_deducts_once(self):
        self.submit(0)
        order = Order.objects.get()
        self.assertEqual(self.parallel([lambda: self.send(order), lambda: self.send(order)]), [302, 302])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertEqual(StockReservation.objects.get().deducted_quantity, 1)

    def test_double_cancel_returns_once(self):
        self.submit(0)
        order = Order.objects.get()
        self.send(order)
        results = self.parallel([lambda: cancel(order.pk, self.tenant), lambda: cancel(order.pk, self.tenant)])
        self.assertEqual(sorted(results), [False, True])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)

    def test_send_racing_cancel_never_leaves_stock_debited(self):
        self.submit(0)
        order = Order.objects.get()
        # If cancellation wins, the send returns a 404 because draft invalidation
        # removes the review. If sending wins, cancellation returns its debit.
        from django.http import Http404
        def send_or_404():
            try:
                return self.send(order)
            except Http404:
                return 404
        self.parallel([send_or_404, lambda: cancel(order.pk, self.tenant)])
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(self.product.stock, 1)
