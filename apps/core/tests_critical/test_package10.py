import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone

from apps.customers.models import Customer
from apps.coupons.models import CouponCampaign, CouponRedemption
from apps.coupons.services import validate_coupon, get_customer_orders_for_tenant
from apps.orders.models import Cart, CartItem, Order
from apps.orders import cart_service as integrity
from apps.stores.models import (
    Product,
    CustomizationGroup,
    CustomizationGroupLabel,
    CustomizationOption,
)
from .base import CriticalTestCase


class Package10Tests(CriticalTestCase):
    def add(self, **data):
        return self.client.post(
            "/checkout/add/",
            json.dumps({"product_id": self.product_a.pk, "quantity": 1, **data}),
            content_type="application/json",
            HTTP_HOST=self.host(self.tenant_a),
        )

    def group(self, **fields):
        label = CustomizationGroupLabel.objects.create(
            tenant=self.tenant_a,
            name="Opções " + str(CustomizationGroup.objects.count()),
        )
        group = CustomizationGroup.objects.create(
            tenant=self.tenant_a, category=self.category_a, label=label, **fields
        )
        option = CustomizationOption.objects.create(
            tenant=self.tenant_a, group=group, name="Extra", price=Decimal("5")
        )
        return group, option

    def choice(self, group, option, **overrides):
        return {"group_id": str(group.pk), "option_id": str(option.pk), **overrides}

    def ready(self):
        response = self.client.get(
            "/checkout/checkout/", HTTP_HOST=self.host(self.tenant_a)
        )
        self.assertEqual(response.status_code, 200)
        return self.client.session["checkout_token"]

    def submit(self, token=None, **extra):
        token = token or self.client.session["checkout_token"]
        return self.client.post(
            "/checkout/checkout/",
            {
                "checkout_token": token,
                "full_name": "Cliente Teste",
                "phone": "11999999999",
                "delivery_type": "pickup",
                "payment_method": "pix",
                **extra,
            },
            HTTP_HOST=self.host(self.tenant_a),
        )

    def login_buyer(self):
        user = get_user_model().objects.create_user(
            username="buyer", email="buyer@example.com", password=self.password
        )
        self.customer = Customer.objects.create(user=user, phone="5511999998888")
        self.client.force_login(user)
        return user

    def campaign(self):
        return CouponCampaign.objects.create(
            tenant=self.tenant_a,
            name="Oferta",
            code="TESTE",
            discount_type="fixed_amount",
            discount_value=Decimal("2"),
            usage_limit=1,
            usage_limit_per_customer=1,
        )

    def test_negative_client_price_and_fake_name_are_ignored(self):
        group, option = self.group()
        result = self.add(
            customizations=[
                self.choice(
                    group, option, price="-10000", option_name="Forjado", min_choices=0
                )
            ]
        )
        self.assertEqual(result.status_code, 200)
        item = CartItem.objects.get()
        self.assertEqual(item.price, Decimal("25"))
        self.assertEqual(
            item.combination_details["customizations"][0]["option_name"], "Extra"
        )
        self.ready()
        self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(Order.objects.get().total, Decimal("25"))

    def test_fake_foreign_inactive_and_duplicate_options_rejected(self):
        group, option = self.group()
        foreign = CustomizationOption.objects.create(
            tenant=self.tenant_b, group=group, name="Foreign", price=1
        )
        for choices in [
            [{"group_id": 999999, "option_id": 999999, "price": "-19"}],
            [self.choice(group, foreign)],
            [self.choice(group, option)] * 2,
        ]:
            with self.subTest(choices=choices):
                self.assertEqual(self.add(customizations=choices).status_code, 400)
        option.is_available = False
        option.save()
        self.assertEqual(
            self.add(customizations=[self.choice(group, option)]).status_code, 400
        )
        self.assertFalse(CartItem.objects.exists())

    def test_required_and_maximum_options_enforced(self):
        group, option = self.group(min_options=1, max_options=1)
        self.assertEqual(self.add().status_code, 400)
        option2 = CustomizationOption.objects.create(group=group, name="Outro", price=2)
        self.assertEqual(
            self.add(
                customizations=[self.choice(group, option), self.choice(group, option2)]
            ).status_code,
            400,
        )
        self.assertEqual(
            self.add(customizations=[self.choice(group, option)]).status_code, 200
        )
        item = CartItem.objects.get()
        response = self.client.post(
            f"/checkout/carrinho/item/{item.pk}/opcional/remover/",
            json.dumps({"bucket": "customizations", "index": 0}),
            content_type="application/json",
            HTTP_HOST=self.host(self.tenant_a),
        )
        self.assertEqual(response.status_code, 400)
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal("25"))

    def test_invalid_quantity_and_json_return_controlled_errors(self):
        for value in [0, -1, 100, True, "abc", 1.2, "1.2", None]:
            with self.subTest(value=value):
                self.assertEqual(self.add(quantity=value).status_code, 400)
        for raw in ["null", "[]", "true", "{"]:
            response = self.client.post(
                "/checkout/add/",
                raw,
                content_type="application/json",
                HTTP_HOST=self.host(self.tenant_a),
            )
            self.assertEqual(response.status_code, 400)
        self.assertFalse(CartItem.objects.exists())

    def test_quantity_update_and_aggregate_limit(self):
        self.product_a.max_order_qty = 2
        self.product_a.save()
        self.assertEqual(self.add(quantity=2).status_code, 200)
        self.assertEqual(self.add(notes="outra variação").status_code, 400)
        item = CartItem.objects.get()
        for value in ["x", 0, -1, 3]:
            response = self.client.post(
                f"/checkout/update_quantity/{item.pk}/",
                {"quantity": value},
                HTTP_HOST=self.host(self.tenant_a),
            )
            self.assertEqual(response.status_code, 400)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_database_rejects_zero_quantity_and_duplicate_cart(self):
        self.add()
        item = CartItem.objects.get()
        cart = item.cart
        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.filter(pk=item.pk).update(quantity=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cart.objects.create(tenant=self.tenant_a, session_key=cart.session_key)

    def test_inactive_store_blocks_add_and_checkout(self):
        self.add()
        token = self.ready()
        self.tenant_a.is_active = False
        self.tenant_a.save()
        self.assertEqual(self.add().status_code, 400)
        self.assertEqual(self.submit(token).status_code, 302)
        self.assertFalse(Order.objects.exists())

    def test_unavailable_product_and_weekday_rechecked(self):
        self.add()
        token = self.ready()
        self.product_a.is_available = False
        self.product_a.save()
        self.assertEqual(self.submit(token).status_code, 302)
        self.assertFalse(Order.objects.exists())
        self.product_a.is_available = True
        self.product_a.available_days = [(timezone.localdate().weekday() + 1) % 7]
        self.product_a.save()
        self.assertEqual(self.add().status_code, 400)

    def test_price_change_requires_new_confirmation(self):
        self.add()
        token = self.ready()
        self.product_a.price = Decimal("30")
        self.product_a.save()
        response = self.submit(token)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(CartItem.objects.get().price, Decimal("30"))
        self.ready()
        self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(Order.objects.get().total, Decimal("30"))

    def test_optional_removal_uses_current_prices(self):
        group, option = self.group()
        self.add(customizations=[self.choice(group, option)])
        self.product_a.price = Decimal("30")
        self.product_a.save()
        item = CartItem.objects.get()
        result = self.client.post(
            f"/checkout/carrinho/item/{item.pk}/opcional/remover/",
            json.dumps({"bucket": "customizations", "index": 0}),
            content_type="application/json",
            HTTP_HOST=self.host(self.tenant_a),
        )
        self.assertEqual(result.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal("30"))

    def test_zero_sale_price_is_respected(self):
        self.product_a.sale_price = Decimal("0")
        self.product_a.save()
        self.add()
        self.ready()
        self.submit()
        self.assertEqual(Order.objects.get().total, 0)
        self.assertEqual(Order.objects.get().items.get().quantity, 1)

    def test_both_half_endpoints_share_prices_and_required_rules(self):
        p2 = Product.objects.create(
            tenant=self.tenant_a,
            category=self.category_a,
            name="Outro",
            price=Decimal("30"),
        )
        group, option = self.group(apply_to="half", min_options=1)
        data = {
            "is_half": True,
            "product_ids": [p2.pk, self.product_a.pk],
            "quantity": 1,
        }
        for url in ["/checkout/add/", "/checkout/checkout/add-half-half/"]:
            response = self.client.post(
                url,
                json.dumps(data),
                content_type="application/json",
                HTTP_HOST=self.host(self.tenant_a),
            )
            self.assertEqual(response.status_code, 400)
            complete = {
                **data,
                "customizations_half1": [self.choice(group, option, price="-500")],
                "customizations_half2": [self.choice(group, option, price=0)],
            }
            response = self.client.post(
                url,
                json.dumps(complete),
                content_type="application/json",
                HTTP_HOST=self.host(self.tenant_a),
            )
            self.assertEqual(response.status_code, 200)
        item = CartItem.objects.get()
        self.assertEqual(item.price, Decimal("40"))
        self.assertEqual(item.quantity, 2)
        self.assertEqual(
            item.combination_details["product_ids"],
            [str(p2.pk), str(self.product_a.pk)],
        )

    def test_half_distinct_category_and_enabled_variant(self):
        p2 = Product.objects.create(
            tenant=self.tenant_a,
            category=self.category_a,
            name="Outro",
            price=Decimal("30"),
        )
        p2.half_variant.is_active = False
        p2.half_variant.save()
        self.assertEqual(
            self.add(is_half=True, product_ids=[self.product_a.pk, p2.pk]).status_code,
            400,
        )
        self.assertEqual(
            self.add(
                is_half=True, product_ids=[self.product_a.pk, self.product_a.pk]
            ).status_code,
            400,
        )
        self.assertEqual(
            self.add(
                is_half=True, product_ids=[self.product_a.pk, self.product_b.pk]
            ).status_code,
            400,
        )

    def test_sequential_checkout_is_idempotent_and_mutation_invalidates_draft(self):
        self.add()
        token = self.ready()
        self.submit(token)
        self.submit(token)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.add(notes="novo")
        order.refresh_from_db()
        self.assertIsNotNone(order.abandoned_at)
        self.assertEqual(self.submit(token).status_code, 400)

    def test_edit_releases_coupon_and_abandoned_orders_do_not_count(self):
        self.login_buyer()
        self.campaign()
        self.add()
        self.ready()
        self.submit(coupon_code="TESTE")
        order = Order.objects.get()
        self.assertEqual(CouponRedemption.objects.count(), 1)
        response = self.client.post(
            f"/pedido/{order.public_token}/editar/", HTTP_HOST=self.host(self.tenant_a)
        )
        self.assertEqual(response.status_code, 302)
        result = validate_coupon(
            code="TESTE",
            tenant=self.tenant_a,
            customer=self.customer,
            subtotal=20,
            delivery_fee=0,
        )
        self.assertTrue(result["valid"])
        self.assertFalse(
            get_customer_orders_for_tenant(self.customer, self.tenant_a).exists()
        )
        self.ready()
        self.assertEqual(self.submit(coupon_code="TESTE").status_code, 200)

    def test_expired_coupon_reservation_is_released_and_cannot_be_sent(self):
        self.login_buyer()
        self.campaign()
        self.add()
        self.ready()
        self.submit(coupon_code="TESTE")
        order = Order.objects.get()
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(minutes=31)
        )
        self.assertTrue(
            validate_coupon(
                code="TESTE",
                tenant=self.tenant_a,
                customer=self.customer,
                subtotal=20,
                delivery_fee=0,
            )["valid"]
        )
        result = self.client.get(
            f"/pedido/{order.public_token}/whatsapp/",
            HTTP_HOST=self.host(self.tenant_a),
        )
        self.assertEqual(result.status_code, 302)
        self.assertFalse(result.url.startswith("https://wa.me"))
        order.refresh_from_db()
        self.assertIsNone(order.whatsapp_opened_at)

    def test_open_commits_coupon_and_reopening_keeps_new_cart(self):
        self.login_buyer()
        self.campaign()
        self.add()
        self.ready()
        self.submit(coupon_code="TESTE")
        order = Order.objects.get()
        url = f"/pedido/{order.public_token}/whatsapp/"
        response = self.client.get(url, HTTP_HOST=self.host(self.tenant_a))
        self.assertTrue(response.url.startswith("https://wa.me"))
        self.assertFalse(
            validate_coupon(
                code="TESTE",
                tenant=self.tenant_a,
                customer=self.customer,
                subtotal=20,
                delivery_fee=0,
            )["valid"]
        )
        self.add()
        self.client.get(url, HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(CartItem.objects.count(), 1)

    def test_price_change_after_review_blocks_whatsapp(self):
        self.add()
        self.ready()
        self.submit()
        order = Order.objects.get()
        self.product_a.price = Decimal("70")
        self.product_a.save()
        response = self.client.get(
            f"/pedido/{order.public_token}/whatsapp/",
            HTTP_HOST=self.host(self.tenant_a),
        )
        self.assertFalse(response.url.startswith("https://wa.me"))
        order.refresh_from_db()
        self.assertIsNone(order.whatsapp_opened_at)
        self.assertEqual(order.total, Decimal("20"))

    def test_foreign_session_cannot_edit_or_send_order(self):
        self.add()
        self.ready()
        self.submit()
        order = Order.objects.get()
        other = Client()
        self.assertEqual(
            other.post(
                f"/pedido/{order.public_token}/editar/",
                HTTP_HOST=self.host(self.tenant_a),
            ).status_code,
            404,
        )
        self.assertEqual(
            other.get(
                f"/pedido/{order.public_token}/whatsapp/",
                HTTP_HOST=self.host(self.tenant_a),
            ).status_code,
            404,
        )

    def test_repeat_reprices_options_and_rejects_disabled_option(self):
        self.login_buyer()
        group, option = self.group()
        self.add(customizations=[self.choice(group, option)])
        self.ready()
        self.submit()
        order = Order.objects.get()
        self.client.get(
            f"/pedido/{order.public_token}/whatsapp/",
            HTTP_HOST=self.host(self.tenant_a),
        )
        option.price = Decimal("8")
        option.save()
        response = self.client.post(
            f"/meus-pedidos/{order.public_token}/repetir/",
            HTTP_HOST=self.host(self.tenant_a),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CartItem.objects.get().price, Decimal("28"))
        CartItem.objects.all().delete()
        option.is_available = False
        option.save()
        self.client.post(
            f"/meus-pedidos/{order.public_token}/repetir/",
            HTTP_HOST=self.host(self.tenant_a),
        )
        self.assertFalse(CartItem.objects.exists())

    def test_add_failure_preserves_session_and_json_error(self):
        response = self.add(quantity=0)
        self.assertEqual(response.status_code, 400)
        self.assertIn("quantidade", response.json()["error"])
        self.assertEqual(self.add().status_code, 200)

    def test_new_required_option_blocks_existing_cart(self):
        self.add()
        token = self.ready()
        self.group(min_options=1)
        response = self.submit(token)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.exists())
        response = self.client.get(
            "/checkout/cart/", HTTP_HOST=self.host(self.tenant_a)
        )
        self.assertContains(response, "Escolha entre")

    def test_half_average_and_scope_rules(self):
        from apps.orders.models import CombinationPricingRule

        p2 = Product.objects.create(
            tenant=self.tenant_a,
            category=self.category_a,
            name="Outro",
            price=Decimal("21.01"),
        )
        CombinationPricingRule.objects.create(
            tenant=self.tenant_a,
            combination_type="half_half",
            price_calculation_method="average",
        )
        group, option = self.group(apply_to="whole")
        data = {"is_half": True, "product_ids": [self.product_a.pk, p2.pk]}
        self.assertEqual(
            self.add(
                **data, customizations_half1=[self.choice(group, option)]
            ).status_code,
            400,
        )
        self.assertEqual(
            self.add(
                **data, customizations_whole=[self.choice(group, option)]
            ).status_code,
            200,
        )
        self.assertEqual(CartItem.objects.get().price, Decimal("25.51"))

    def test_disabled_coupon_after_review_is_not_sent(self):
        self.login_buyer()
        campaign = self.campaign()
        self.add()
        self.ready()
        self.submit(coupon_code="TESTE")
        order = Order.objects.get()
        campaign.is_active = False
        campaign.save()
        response = self.client.get(
            f"/pedido/{order.public_token}/whatsapp/",
            HTTP_HOST=self.host(self.tenant_a),
        )
        self.assertFalse(response.url.startswith("https://wa.me"))
        order.refresh_from_db()
        self.assertIsNotNone(order.abandoned_at)

    def test_minimum_quantity_and_foreign_category(self):
        group, option = self.group()
        group.category = self.category_b
        group.save()
        self.assertEqual(
            self.add(customizations=[self.choice(group, option)]).status_code, 400
        )
        self.product_a.min_order_qty = 2
        self.product_a.save()
        self.assertEqual(self.add(quantity=1).status_code, 400)
        self.assertEqual(self.add(quantity=2).status_code, 200)

    def test_invalid_catalog_option_price_rejected(self):
        group, option = self.group()
        option.price = Decimal("-1")
        option.save()
        response = self.add(customizations=[self.choice(group, option)])
        self.assertEqual(response.status_code, 400)
        self.assertIn("preço inválido", response.json()["error"])
        self.assertFalse(CartItem.objects.exists())

    def test_delivery_fee_is_revalidated_before_opening(self):
        self.add()
        self.ready()
        self.assertEqual(
            self.submit(
                delivery_type="delivery",
                address="Rua Teste",
                number="1",
                neighborhood="Vila Mariana",
                city="São Paulo",
            ).status_code,
            200,
        )
        order = Order.objects.get()
        self.zone_a.fee = Decimal("9")
        self.zone_a.save()
        result = self.client.get(
            f"/pedido/{order.public_token}/whatsapp/",
            HTTP_HOST=self.host(self.tenant_a),
        )
        self.assertFalse(result.url.startswith("https://wa.me"))
        order.refresh_from_db()
        self.assertIsNone(order.whatsapp_opened_at)

    def test_editing_notes_does_not_merge_a_later_different_item(self):
        self.add()
        item = CartItem.objects.get()
        result = self.client.post(
            f"/checkout/update_notes/{item.pk}/",
            {"notes": "Sem cebola"},
            HTTP_HOST=self.host(self.tenant_a),
        )
        self.assertEqual(result.status_code, 200)
        self.add()
        self.assertEqual(CartItem.objects.count(), 2)
        item.refresh_from_db()
        self.assertEqual(item.notes, "Sem cebola")
        self.assertEqual(item.quantity, 1)
