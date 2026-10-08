import json
from unittest.mock import patch
from django.test import Client, override_settings
from django.urls import reverse
from .base import CriticalTestCase


class PublicReactTests(CriticalTestCase):
    def get_json(self, path='/', **kwargs):
        return self.client.get(path, HTTP_HOST=self.host(self.tenant_a), HTTP_ACCEPT='application/json', **kwargs)

    def test_catalog_contract_scopes_tenant_and_serializes_prices(self):
        result = self.get_json()
        self.assertEqual(result.status_code, 200)
        data = result.json()
        self.assertEqual(data['page'], 'catalog')
        self.assertEqual(data['props']['categories'][0]['products'][0]['price'], '20.00')
        self.assertNotIn(self.product_b.name, result.content.decode())
        self.assertIn('no-store', result['Cache-Control'])
        self.assertTrue(data['csrf'])

    def test_password_is_never_serialized_on_invalid_login(self):
        result = self.client.post('/conta/entrar/', {'email': 'unknown@example.com', 'password': 'private-do-not-echo'}, HTTP_ACCEPT='application/json')
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('private-do-not-echo', result.content.decode())
        self.assertTrue(result.json()['props']['form']['errors'])

    def test_public_json_does_not_disable_csrf(self):
        result = Client(enforce_csrf_checks=True).post('/checkout/add/', json.dumps({'product_id': self.product_a.pk, 'quantity': 1}), content_type='application/json', HTTP_HOST=self.host(self.tenant_a), HTTP_ACCEPT='application/json')
        self.assertEqual(result.status_code, 403)

    def test_checkout_still_rejects_forged_cart_token(self):
        result = self.client.post('/checkout/checkout/', {'checkout_token': 'fake'}, HTTP_HOST=self.host(self.tenant_a), HTTP_ACCEPT='application/json')
        self.assertEqual(result.status_code, 400)

    def test_rendered_catalog_has_content_without_javascript(self):
        result = self.client.get('/', HTTP_HOST=self.host(self.tenant_a))
        self.assertContains(result, '<div id="public-root">', html=False)
        self.assertContains(result, self.product_a.name)
        self.assertContains(result, 'application/json')

    def test_legal_pages_have_no_private_store_payload(self):
        data = self.get_json('/termos/').json()
        self.assertIsNone(data['store'])
        self.assertEqual(data['page'], 'terms')

    def test_ssr_failure_is_explicit_and_never_returns_empty_spa(self):
        import requests
        with patch('apps.public_ui.rendering.requests.Session.post', side_effect=requests.ConnectionError):
            result = self.client.get('/', HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(result.status_code, 503)
        self.assertNotIn('public-root', result.content.decode())


@override_settings(MERCHANT_REACT_ENABLED=True, LEGACY_ADMIN_ENABLED=False)
class ReactCutoverTests(CriticalTestCase):
    def test_legacy_get_redirects_and_posts_are_not_executed(self):
        client=Client(HTTP_HOST=self.host(self.tenant_a))
        client.force_login(self.admin_a)
        self.assertEqual(client.get('/admin/')['Location'],'/painel/')
        self.assertEqual(client.post('/admin/').status_code,409)
        root=Client(HTTP_HOST='vemdedelivery.com.br')
        root.force_login(self.superuser)
        self.assertEqual(root.get('/superadmin-legacy/')['Location'],'/painel/')
        self.assertEqual(root.post('/superadmin-legacy/').status_code,409)
