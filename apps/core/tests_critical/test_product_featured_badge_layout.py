from pathlib import Path

from django.conf import settings

from .base import CriticalTestCase


class ProductFeaturedBadgeLayoutCriticalTests(CriticalTestCase):
    def test_featured_badge_is_positioned_at_right_edge_of_product_content(self):
        self.product_a.is_featured = True
        self.product_a.save(update_fields=["is_featured"])

        response = self.client.get(
            "/",
            HTTP_HOST=self.host(self.tenant_a),
        )

        self.assertEqual(response.status_code, 200)

        html = response.content.decode("utf-8")

        # Confirma que o produto continua marcado como destaque.
        self.assertIn("product-card-featured", html)
        self.assertIn("catalog-featured-v2", html)
        self.assertIn("★ Destaque", html)

        # Confirma que o estilo de posicionamento está definido.
        css_path = (
            Path(settings.BASE_DIR)
            / "frontend"
            / "src"
            / "public"
            / "storefront.css"
        )

        self.assertTrue(css_path.is_file())

        css = css_path.read_text(encoding="utf-8")

        self.assertRegex(
            css,
            r"\.storefront\s+\.catalog-featured-v2\s*\{[^}]*float\s*:\s*right\s*;",
        )
