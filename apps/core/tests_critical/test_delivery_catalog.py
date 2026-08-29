from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.stores.models import Product
from apps.tenants.choices import FulfillmentMode
from apps.tenants.delivery import normalize_location_text, resolve_delivery

from .base import CriticalTestCase


class DeliveryAndCatalogCriticalTests(CriticalTestCase):
    def test_location_normalization_ignores_accents_case_and_spaces(self):
        self.assertEqual(normalize_location_text("  VÍLA   Mariána "), "vila mariana")

    def test_delivery_zone_matches_normalized_address(self):
        result = resolve_delivery(self.tenant_a, "delivery", city=" sao   PAULO ", neighborhood="VÍLA MARIANA")
        self.assertTrue(result["available"])
        self.assertEqual(result["source"], "delivery_zone")
        self.assertEqual(result["fee"], Decimal("7.50"))

    def test_other_tenant_delivery_zone_is_not_used(self):
        result = resolve_delivery(self.tenant_a, "delivery", city="São Paulo", neighborhood="Moema")
        self.assertFalse(result["available"])
        self.assertEqual(result["source"], "not_served")

    def test_pickup_always_has_zero_fee(self):
        result = resolve_delivery(self.tenant_a, "pickup", city="", neighborhood="")
        self.assertTrue(result["available"])
        self.assertEqual(result["fee"], Decimal("0.00"))
        self.assertEqual(result["source"], "pickup")

    def test_delivery_only_rules_are_enforced(self):
        self.tenant_a.fulfillment_mode = FulfillmentMode.PICKUP_ONLY
        self.tenant_a.save()
        result = resolve_delivery(self.tenant_a, "delivery", city="São Paulo", neighborhood="Vila Mariana")
        self.assertFalse(result["available"])
        self.assertEqual(result["source"], "delivery_disabled")

    def test_product_cannot_use_category_from_other_tenant(self):
        product = Product(tenant=self.tenant_a, category=self.category_b, name="Produto inválido", price=Decimal("10.00"))
        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_catalog_only_exposes_current_tenant_products(self):
        response = self.client.get("/", HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product_a.name)
        self.assertNotContains(response, self.product_b.name)
