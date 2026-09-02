from unittest.mock import patch
from django.core.cache import cache
from django.test import Client, RequestFactory, override_settings
from apps.core.rate_limit import get_client_ip
from .base import CriticalTestCase


@override_settings(ADMIN_LOGIN_ACCOUNT_LIMIT=2, ADMIN_LOGIN_IP_LIMIT=20, ADMIN_LOGIN_WINDOW=60,
                   OTP_TRUST_PROXY_HEADERS=False)
class AdminSecurityTests(CriticalTestCase):
    def setUp(self):
        cache.clear()

    def post(self, user='invalid', password='bad', path='/admin/login/', host=None, **headers):
        return self.client.post(path, {'username': user, 'password': password, 'next': '/admin/'},
                                HTTP_HOST=host or self.host(self.tenant_a), **headers)

    def test_tenant_limit_blocks_even_valid_password_until_expiry(self):
        for _ in range(2):
            self.assertEqual(self.post(user=self.admin_a.username).status_code, 200)
        response = self.post(user=self.admin_a.username, password=self.password)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '60')
        self.assertContains(response, 'Muitas tentativas', status_code=429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_superadmin_limit_applies_to_html_form(self):
        for _ in range(2):
            self.post(path='/superadmin/login/', host='vemdedelivery.com.br')
        self.assertEqual(self.post(path='/superadmin/login/', host='vemdedelivery.com.br').status_code, 429)

    def test_account_limit_survives_ip_rotation(self):
        self.post(REMOTE_ADDR='192.0.2.1')
        self.post(REMOTE_ADDR='192.0.2.2')
        self.assertEqual(self.post(REMOTE_ADDR='192.0.2.3').status_code, 429)

    @override_settings(ADMIN_LOGIN_IP_LIMIT=2)
    def test_ip_limit_survives_username_rotation_and_forged_headers(self):
        self.post(user='a', HTTP_X_REAL_IP='192.0.2.1')
        self.post(user='b', HTTP_X_REAL_IP='192.0.2.2')
        self.assertEqual(self.post(user='c', HTTP_X_REAL_IP='192.0.2.3').status_code, 429)

    def test_tenant_scopes_are_separate(self):
        self.post(); self.post()
        self.assertEqual(self.post(host=self.host(self.tenant_b)).status_code, 200)

    def test_cache_failure_fails_closed_without_exception_details(self):
        with patch('apps.tenants.admin_security.rate_limit_exceeded', side_effect=RuntimeError('SECRET')):
            response = self.post(user=self.admin_a.username, password=self.password)
        self.assertContains(response, 'temporariamente indisponível', status_code=503)
        self.assertNotContains(response, 'SECRET', status_code=503)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_authorized_logins_and_forbidden_admin_role(self):
        self.assertEqual(self.post(user=self.admin_a.username, password=self.password).status_code, 302)
        self.client.logout()
        self.assertEqual(self.post(user=self.admin_a.username, password=self.password, path='/superadmin/login/', host='vemdedelivery.com.br').status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.post(user=self.superuser.username, password=self.password, path='/superadmin/login/', host='vemdedelivery.com.br').status_code, 302)

    def test_staff_without_tenant_admin_role_cannot_use_existing_session(self):
        self.admin_a.is_tenant_admin = False
        self.admin_a.save()
        self.client.force_login(self.admin_a)
        response = self.client.get('/admin/', HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_csrf_rejected_before_counters(self):
        client = Client(enforce_csrf_checks=True)
        with patch('apps.tenants.admin_security.rate_limit_exceeded') as counter:
            response = client.post('/admin/login/', {'username': 'a', 'password': 'b'}, HTTP_HOST=self.host(self.tenant_a))
        self.assertEqual(response.status_code, 403)
        counter.assert_not_called()

    @override_settings(OTP_TRUST_PROXY_HEADERS=True, OTP_TRUSTED_PROXY_CIDRS=['172.20.0.0/24'])
    def test_only_trusted_proxy_can_supply_real_ip(self):
        factory = RequestFactory()
        request = factory.get('/', REMOTE_ADDR='192.0.2.1', HTTP_X_REAL_IP='203.0.113.1')
        self.assertEqual(get_client_ip(request), '192.0.2.1')
        request.META['REMOTE_ADDR'] = '172.20.0.3'
        self.assertEqual(get_client_ip(request), '203.0.113.1')
        request.META['HTTP_X_REAL_IP'] = 'not-an-ip'
        self.assertEqual(get_client_ip(request), 'unknown')
