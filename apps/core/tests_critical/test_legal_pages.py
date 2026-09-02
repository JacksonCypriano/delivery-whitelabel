from django.urls import reverse
from .base import CriticalTestCase


class LegalPagesTests(CriticalTestCase):
    def test_pages_are_public_and_identify_platform_and_backup_app(self):
        for route, title in [('privacy', 'Política de Privacidade'), ('terms', 'Termos de Serviço')]:
            with self.subTest(route=route):
                response = self.client.get(reverse('marketplace:' + route), HTTP_HOST='vemdedelivery.com.br')
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, title)
                self.assertContains(response, 'VemDeDelivery Backups')
                self.assertContains(response, '59.198.345/0001-44')
                self.assertContains(response, 'mailto:backupvemdedelivery@gmail.com')
                self.assertContains(response, 'logo-vemdedelivery.svg')

    def test_tenant_hosts_can_read_same_public_policies(self):
        for route in ('privacy', 'terms'):
            response = self.client.get(reverse('marketplace:' + route), HTTP_HOST=self.host(self.tenant_a))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'COBRADEV SOLUTIONS')
            self.assertNotContains(response, 'csrfmiddlewaretoken')

    def test_legal_pages_are_read_only(self):
        for route in ('privacy', 'terms'):
            path = reverse('marketplace:' + route)
            self.assertEqual(self.client.head(path, HTTP_HOST='vemdedelivery.com.br').status_code, 200)
            self.assertEqual(self.client.post(path, {}, HTTP_HOST='vemdedelivery.com.br').status_code, 405)

    def test_home_and_customer_footer_link_to_policies(self):
        for path in ('/', '/conta/entrar/'):
            response = self.client.get(path, HTTP_HOST='vemdedelivery.com.br')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '/privacidade/')
            self.assertContains(response, '/termos/')
