import json
import re
from html import unescape
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse

from apps.marketplace import marketing_views
from apps.marketplace.marketing_content import MARKETING_PAGES


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=[".vemdedelivery.com.br", "testserver"],
    MARKETING_PUBLIC_URL="https://vemdedelivery.com.br",
)
class MarketingLandingTests(SimpleTestCase):
    def request(self, path="/para-lojistas/?utm_source=google", host="vemdedelivery.com.br", tenant=None):
        request = RequestFactory().get(path, HTTP_HOST=host)
        request.tenant = tenant
        return request

    @staticmethod
    def schema(html):
        return json.loads(re.search(r'application/ld\+json">(.*?)</script>', html).group(1))

    def test_production_content_canonical_agent_and_schema(self):
        response = marketing_views.landing(self.request())
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('content="index, follow"', html)
        self.assertIn('href="https://vemdedelivery.com.br/para-lojistas/"', html)
        self.assertEqual(html.count("<h1>"), 1)
        self.assertIn("R$ 149", html)
        self.assertIn("agente no whatsapp", html.lower())
        self.assertIn("Carrinho e checkout", html)
        self.assertIn("pet shops", html.lower())
        self.assertIn('property="og:image"', html)
        self.assertIn('href="https://demo.vemdedelivery.com.br/"', html)
        self.assertNotIn("vitrine-demo.vemdedelivery.com.br", html)

        schema = self.schema(html)
        graph = schema["@graph"]
        application = next(item for item in graph if item["@type"] == "SoftwareApplication")
        organization = next(item for item in graph if item["@type"] == "Organization")
        self.assertEqual(application["offers"]["price"], "149.00")
        self.assertEqual(organization["legalName"], "COBRADEV SOLUTIONS")
        self.assertNotIn("aggregateRating", html)

    def test_every_editorial_page_has_unique_metadata_canonical_and_h1(self):
        titles = set()
        descriptions = set()
        for key, page in MARKETING_PAGES.items():
            with self.subTest(page=key):
                response = marketing_views.seo_page(
                    self.request("/" + page["path"] + "?utm_campaign=seo"), key
                )
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                canonical = "https://vemdedelivery.com.br/" + page["path"]
                self.assertIn(f'href="{canonical}"', html)
                self.assertEqual(html.count("<h1>"), 1)
                self.assertIn(page["title"], html)
                self.assertIn(page["description"], html)
                self.assertIn("R$ 149", html)
                self.assertIn("WhatsApp", html)
                titles.add(page["title"])
                descriptions.add(page["description"])

        self.assertEqual(len(titles), len(MARKETING_PAGES))
        self.assertEqual(len(descriptions), len(MARKETING_PAGES))

    def test_requested_and_non_food_routes_exist(self):
        expected = {
            "/cardapio-online/": "marketplace:cardapio_online",
            "/delivery-sem-comissao/": "marketplace:delivery_sem_comissao",
            "/pedidos-pelo-whatsapp/": "marketplace:pedidos_pelo_whatsapp",
            "/agente-whatsapp-delivery/": "marketplace:agente_whatsapp_delivery",
            "/sistema-para-pizzaria/": "marketplace:sistema_para_pizzaria",
            "/sistema-para-hamburgueria/": "marketplace:sistema_para_hamburgueria",
            "/sistema-para-marmitaria/": "marketplace:sistema_para_marmitaria",
            "/sistema-para-mercado/": "marketplace:sistema_para_mercado",
            "/sistema-para-mercadinho/": "marketplace:sistema_para_mercadinho",
            "/sistema-para-pet-shop/": "marketplace:sistema_para_pet_shop",
            "/sistema-para-casa-de-racao/": "marketplace:sistema_para_casa_racao",
            "/sistema-para-floricultura/": "marketplace:sistema_para_floricultura",
        }
        for path, view_name in expected.items():
            with self.subTest(path=path):
                self.assertEqual(resolve(path).view_name, view_name)

    def test_staging_tenant_and_debug_are_not_indexed(self):
        for host, tenant in [
            ("homolog.vemdedelivery.com.br", None),
            ("demo.vemdedelivery.com.br", SimpleNamespace()),
            ("testserver", None),
        ]:
            with self.subTest(host=host):
                request = self.request(host=host, tenant=tenant)
                self.assertEqual(marketing_views.landing(request)["X-Robots-Tag"], "noindex, follow")
                self.assertEqual(marketing_views.sitemap_index(request).status_code, 404)
                self.assertEqual(marketing_views.marketing_sitemap(request).status_code, 404)
                self.assertIn("Disallow: /", marketing_views.robots_txt(request).content.decode())

                page_key = "sistema-para-pet-shop"
                page_response = marketing_views.seo_page(request, page_key)
                self.assertEqual(page_response["X-Robots-Tag"], "noindex, follow")

    @override_settings(DEBUG=True)
    def test_debug_not_indexed(self):
        self.assertEqual(marketing_views.landing(self.request())["X-Robots-Tag"], "noindex, follow")

    def test_primary_sitemap_is_an_index_for_marketing_sitemap(self):
        response = marketing_views.sitemap_index(self.request("/sitemap.xml"))
        root = ElementTree.fromstring(response.content)
        locations = root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
        self.assertEqual(
            [item.text for item in locations],
            ["https://vemdedelivery.com.br/sitemap-lojistas.xml"],
        )

    def test_sitemap_contains_landing_and_every_editorial_page(self):
        response = marketing_views.marketing_sitemap(self.request())
        root = ElementTree.fromstring(response.content)
        locations = [
            item.text
            for item in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
        ]
        expected = ["https://vemdedelivery.com.br/para-lojistas/"] + [
            "https://vemdedelivery.com.br/" + page["path"]
            for page in MARKETING_PAGES.values()
        ]
        self.assertEqual(locations, expected)
        self.assertEqual(len(locations), 1 + len(MARKETING_PAGES))
        self.assertEqual(len(locations), len(set(locations)))

    def test_robots_points_to_primary_sitemap_and_blocks_private_areas(self):
        text = marketing_views.robots_txt(self.request("/robots.txt")).content.decode()
        self.assertIn("Sitemap: https://vemdedelivery.com.br/sitemap.xml", text)
        self.assertIn("Disallow: /admin/", text)
        self.assertIn("Disallow: /superadmin/", text)
        self.assertIn("Disallow: /checkout/", text)
        self.assertIn("Allow: /", text)

    def test_routes_preserve_marketplace_and_legacy_sitemap(self):
        self.assertEqual(resolve("/").view_name, "marketplace:home")
        self.assertEqual(resolve("/para-lojistas/").view_name, "marketplace:for_merchants")
        self.assertEqual(reverse("marketplace:sitemap"), "/sitemap.xml")
        self.assertEqual(reverse("marketplace:marketing_sitemap"), "/sitemap-lojistas.xml")
        self.assertEqual(resolve("/robots.txt").view_name, "marketplace:robots_txt")

    def test_ctas_use_official_whatsapp_and_legal_links_are_present(self):
        html = marketing_views.landing(self.request()).content.decode()
        links = re.findall(r'href="([^"]+)"', html)
        contacts = [unescape(link) for link in links if link.startswith("https://wa.me/")]
        self.assertGreaterEqual(len(contacts), 4)
        for contact in contacts:
            self.assertEqual(urlsplit(contact).path, "/5511964059470")
            self.assertIn("contratar", parse_qs(urlsplit(contact).query)["text"][0])
        self.assertIn("/privacidade/", links)
        self.assertIn("/termos/", links)

    def test_post_is_rejected(self):
        post = RequestFactory().post("/para-lojistas/")
        post.tenant = None
        self.assertEqual(marketing_views.landing(post).status_code, 405)
        self.assertEqual(marketing_views.sitemap_index(post).status_code, 405)
        self.assertEqual(marketing_views.marketing_sitemap(post).status_code, 405)
        self.assertEqual(marketing_views.robots_txt(post).status_code, 405)
        self.assertEqual(marketing_views.seo_page(post, "cardapio-online").status_code, 405)
