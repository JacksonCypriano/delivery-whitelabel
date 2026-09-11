from decimal import Decimal

from apps.stores.models import Category, Product

from .base import CriticalTestCase


class CatalogPresentationCriticalTests(CriticalTestCase):
    def test_sale_price_is_rendered_and_used_by_catalog_actions(self):
        self.product_a.sale_price = Decimal("15.00")
        self.product_a.save(update_fields=["sale_price"])

        response = self.client.get("/", HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")

        self.assertContains(response, "R$ 15,00")
        self.assertContains(response, "OFERTA")
        self.assertIn('data-product-price="15.00"', html)

    def test_zero_sale_price_is_preserved_by_effective_price(self):
        self.product_a.sale_price = Decimal("0.00")
        self.product_a.save(update_fields=["sale_price"])
        self.assertEqual(self.product_a.effective_price, Decimal("0.00"))
        self.assertTrue(self.product_a.has_discount)

    def test_empty_unavailable_category_is_not_rendered(self):
        category = Category.objects.create(
            tenant=self.tenant_a,
            name="Categoria antiga",
            display_order=1,
        )
        Product.objects.create(
            tenant=self.tenant_a,
            category=category,
            name="Produto antigo",
            price=Decimal("10.00"),
            is_available=False,
        )

        response = self.client.get("/", HTTP_HOST=self.host(self.tenant_a))
        self.assertNotContains(response, "Categoria antiga")
        self.assertNotContains(response, "Produto antigo")

    def test_categories_respect_display_order(self):
        first = Category.objects.create(
            tenant=self.tenant_a,
            name="Primeira categoria",
            display_order=1,
        )
        second = Category.objects.create(
            tenant=self.tenant_a,
            name="Segunda categoria",
            display_order=2,
        )
        Product.objects.create(
            tenant=self.tenant_a,
            category=first,
            name="Produto primeiro",
            price=Decimal("10.00"),
        )
        Product.objects.create(
            tenant=self.tenant_a,
            category=second,
            name="Produto segundo",
            price=Decimal("10.00"),
        )
        self.category_a.display_order = 99
        self.category_a.save(update_fields=["display_order"])

        response = self.client.get("/", HTTP_HOST=self.host(self.tenant_a))
        html = response.content.decode("utf-8")
        self.assertLess(html.index("Primeira categoria"), html.index("Segunda categoria"))
        self.assertLess(html.index("Segunda categoria"), html.index("Lanches"))

    def test_product_metadata_badges_are_visible(self):
        self.product_a.is_vegan = True
        self.product_a.is_spicy = True
        self.product_a.prep_time = 18
        self.product_a.weight = Decimal("320")
        self.product_a.calories = 650
        self.product_a.save(
            update_fields=["is_vegan", "is_spicy", "prep_time", "weight", "calories"]
        )

        response = self.client.get("/", HTTP_HOST=self.host(self.tenant_a))
        self.assertContains(response, "Vegano")
        self.assertContains(response, "Picante")
        self.assertContains(response, "~18 min")
        self.assertContains(response, "320 g")
        self.assertContains(response, "650 kcal")
