from .base import CriticalTestCase


class ProductFeaturedBadgeLayoutCriticalTests(CriticalTestCase):
    def test_featured_badge_is_positioned_at_right_edge_of_product_content(self):
        self.product_a.is_featured = True
        self.product_a.save(update_fields=["is_featured"])

        response = self.client.get("/", HTTP_HOST=self.host(self.tenant_a))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")

        self.assertIn("product-card-featured", html)
        self.assertIn("product-featured absolute top-3 right-3", html)
        self.assertNotIn("product-featured absolute top-3 left-3", html)
