import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import Client
from django.utils import timezone

from apps.orders.models import Cart, Order, StockReservation, CombinationPricingRule
from apps.orders.inventory import active_reservations, cancel
from apps.stores.models import Product
from .base import CriticalTestCase


class InventoryTests(CriticalTestCase):
    def setUp(self):
        self.host_a = self.host(self.tenant_a)
        Product.objects.filter(pk=self.product_a.pk).update(stock=2)

    def add(self, client=None, **extra):
        return (client or self.client).post('/checkout/add/', json.dumps({'product_id': self.product_a.pk, 'quantity': 1, **extra}), content_type='application/json', HTTP_HOST=self.host_a)

    def checkout(self, client=None):
        client = client or self.client
        response = client.get('/checkout/checkout/', HTTP_HOST=self.host_a)
        if response.status_code != 200:
            return response
        return client.post('/checkout/checkout/', {'checkout_token': client.session['checkout_token'], 'full_name': 'Cliente', 'phone': '11988887777', 'delivery_type': 'pickup', 'payment_method': 'pix'}, HTTP_HOST=self.host_a)

    def send(self, order, client=None):
        return (client or self.client).post(f'/pedido/{order.public_token}/whatsapp/', HTTP_HOST=self.host_a)

    def stock(self):
        self.product_a.refresh_from_db()
        return self.product_a.stock

    def test_zero_stock_rejected_with_product_name(self):
        Product.objects.filter(pk=self.product_a.pk).update(stock=0)
        response = self.add()
        self.assertEqual(response.status_code, 400)
        self.assertIn(self.product_a.name, response.json()['error'])

    def test_null_stock_remains_unlimited(self):
        Product.objects.filter(pk=self.product_a.pk).update(stock=None)
        self.assertEqual(self.add(quantity=20).status_code, 200)
        self.assertEqual(self.checkout().status_code, 200)
        self.assertEqual(self.send(Order.objects.get()).status_code, 302)
        self.assertIsNone(self.stock())
        self.assertEqual(StockReservation.objects.get().deducted_quantity, 0)

    def test_stock_aggregates_product_variations(self):
        self.assertEqual(self.add(quantity=2, notes='primeiro').status_code, 200)
        self.assertEqual(self.add(notes='segundo').status_code, 400)
        self.assertEqual(Cart.objects.get().items.count(), 1)

    def test_review_reserves_without_deducting_and_blocks_another_checkout(self):
        other = Client()
        self.add(quantity=2)
        self.add(client=other)
        self.assertEqual(self.checkout().status_code, 200)
        self.assertEqual(self.stock(), 2)
        self.assertEqual(active_reservations().get().quantity, 2)
        response = self.checkout(other)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)

    def test_edit_releases_reservation_and_keeps_physical_stock(self):
        self.add(quantity=2); self.checkout()
        order = Order.objects.get()
        self.client.post(f'/pedido/{order.public_token}/editar/', HTTP_HOST=self.host_a)
        self.assertFalse(active_reservations().exists())
        self.assertEqual(self.stock(), 2)
        self.assertEqual(self.add(Client(), quantity=2).status_code, 200)

    def test_expired_reservation_does_not_require_cleanup_job(self):
        self.add(quantity=2); self.checkout()
        Order.objects.update(created_at=timezone.now() - timedelta(minutes=31))
        other = Client()
        self.assertEqual(self.add(other, quantity=2).status_code, 200)
        self.assertEqual(self.checkout(other).status_code, 200)
        self.assertEqual(active_reservations().count(), 1)
        old = Order.objects.order_by('pk').first()
        self.assertFalse(self.send(old).url.startswith('https://wa.me/'))
        self.assertEqual(self.stock(), 2)

    def test_send_deducts_once_and_reopen_preserves_new_cart(self):
        self.add(); self.checkout()
        order = Order.objects.get()
        self.assertTrue(self.send(order).url.startswith('https://wa.me/'))
        self.assertEqual(self.stock(), 1)
        self.add()
        self.assertTrue(self.send(order).url.startswith('https://wa.me/'))
        self.assertEqual(self.stock(), 1)
        self.assertEqual(Cart.objects.get().items.count(), 1)

    def test_get_link_and_missing_csrf_cannot_deduct_stock(self):
        self.add(); self.checkout()
        order = Order.objects.get()
        url = f'/pedido/{order.public_token}/whatsapp/'
        self.assertEqual(self.client.get(url, HTTP_HOST=self.host_a).status_code, 200)
        guarded = Client(enforce_csrf_checks=True)
        guarded.cookies = self.client.cookies
        self.assertEqual(guarded.post(url, HTTP_HOST=self.host_a).status_code, 403)
        self.assertEqual(self.stock(), 2)
        order.refresh_from_db()
        self.assertIsNone(order.whatsapp_opened_at)

    def test_reduced_stock_blocks_send_and_releases_reservation(self):
        self.add(quantity=2); self.checkout()
        order = Order.objects.get()
        Product.objects.filter(pk=self.product_a.pk).update(stock=1)
        response = self.send(order)
        self.assertFalse(response.url.startswith('https://wa.me/'))
        self.assertFalse(active_reservations().exists())
        self.assertEqual(self.stock(), 1)
        order.refresh_from_db()
        self.assertIsNone(order.whatsapp_opened_at)
        self.assertTrue(Cart.objects.get().items.exists())

    def test_cancel_returns_deducted_stock_only_once(self):
        self.add(quantity=2); self.checkout()
        order = Order.objects.get(); self.send(order)
        self.assertEqual(self.stock(), 0)
        self.assertTrue(cancel(order.pk, self.tenant_a))
        self.assertEqual(self.stock(), 2)
        self.assertFalse(cancel(order.pk, self.tenant_a))
        self.assertEqual(self.stock(), 2)
        self.assertFalse(self.send(order).url.startswith('https://wa.me/'))

    def test_cancel_draft_releases_without_adding_stock_and_rotates_token(self):
        self.add(quantity=2); self.checkout()
        order = Order.objects.get()
        token = Cart.objects.get().checkout_token
        cancel(order.pk, self.tenant_a)
        self.assertFalse(active_reservations().exists())
        self.assertEqual(self.stock(), 2)
        self.assertNotEqual(Cart.objects.get().checkout_token, token)
        self.assertEqual(self.checkout().status_code, 200)

    def test_cannot_cancel_other_store_order(self):
        self.add(); self.checkout()
        with self.assertRaises(Order.DoesNotExist):
            cancel(Order.objects.get().pk, self.tenant_b)
        self.assertEqual(self.stock(), 2)

    def test_legacy_sent_order_never_debits_or_returns_stock(self):
        self.add(); self.checkout()
        order = Order.objects.get()
        order.stock_reservations.all().delete()
        order.whatsapp_opened_at = timezone.now()
        order.save(update_fields=['whatsapp_opened_at'])
        self.send(order)
        self.assertEqual(self.stock(), 2)
        cancel(order.pk, self.tenant_a)
        self.assertEqual(self.stock(), 2)

    def test_half_uses_highest_price_and_half_unit_of_each_product(self):
        other = Product.objects.create(tenant=self.tenant_a, category=self.category_a, name='Pizza mais cara', price=35, stock=1)
        CombinationPricingRule.objects.create(tenant=self.tenant_a, combination_type='half_half', price_calculation_method='average')
        self.assertEqual(self.add(is_half=True, product_ids=[self.product_a.pk, other.pk]).status_code, 200)
        self.assertEqual(self.checkout().status_code, 200)
        order = Order.objects.get()
        self.assertEqual(order.subtotal, Decimal('35'))
        self.assertEqual(set(order.stock_reservations.values_list('quantity', flat=True)), {Decimal('0.5')})
        self.send(order)
        other.refresh_from_db()
        self.assertEqual(other.stock, Decimal('0.5'))
        self.assertEqual(self.stock(), Decimal('1.5'))
        cancel(order.pk, self.tenant_a)
        self.assertEqual(self.stock(), 2)
        other.refresh_from_db()
        self.assertEqual(other.stock, 1)

    def test_failure_during_stock_write_rolls_back_deduction(self):
        self.add(); self.checkout()
        order = Order.objects.get()
        with patch.object(StockReservation, 'save', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                self.send(order)
        self.assertEqual(self.stock(), 2)
        order.refresh_from_db()
        self.assertIsNone(order.whatsapp_opened_at)

    def test_admin_cancel_requires_confirmation_and_restores_stock(self):
        self.add(); self.checkout()
        order = Order.objects.get(); self.send(order)
        self.client.force_login(self.admin_a)
        data = {'action': 'cancel_orders', '_selected_action': [str(order.pk)]}
        response = self.client.post('/admin/orders/order/', data, HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Confirmar cancelamento')
        self.assertEqual(self.stock(), 1)
        response = self.client.post('/admin/orders/order/', {**data, 'confirm_cancel': '1'}, HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.stock(), 2)
