from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.marketplace.services import build_tenant_url

from .base import CriticalTestCase


class TenantStorefrontBrandingCriticalTests(CriticalTestCase):
    def setUp(self):
        self.client.force_login(self.admin_a)

    def test_vemdedelivery_institutional_footer_is_hidden_on_tenant_site(self):
        request = RequestFactory().get("/")
        request.tenant = self.tenant_a

        html = render_to_string(
            "includes/customer_brand_footer.html",
            request=request,
        )

        self.assertEqual(html.strip(), "")

    def test_platform_footer_still_exists_outside_tenant_site(self):
        request = RequestFactory().get("/")
        request.tenant = None

        html = render_to_string(
            "includes/customer_brand_footer.html",
            request=request,
        )

        self.assertIn("COBRADEV SOLUTIONS", html)
        self.assertIn("VemDeDelivery", html)

    def test_tenant_admin_has_public_store_button_opening_new_tab(self):
        response = self.client.get(
            "/admin/",
            HTTP_HOST=self.host(self.tenant_a),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ver minha loja")
        self.assertContains(response, 'target="_blank"', html=False)
        self.assertContains(
            response,
            f'href="{build_tenant_url(self.tenant_a)}"',
            html=False,
        )
