from io import StringIO
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from apps.channels.models import Connection
from apps.tenants.models import Tenant


class Bind99FoodSandboxTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug='vitrine-demo', name='Demo', whatsapp_number='5511999999911')
        self.options = dict(tenant_slug='vitrine-demo', app_shop_id='vdd-vitrine-demo', shop_id='5764619171284910575')

    def run_bind(self, **kwargs):
        return call_command('bind_99food_sandbox', stdout=StringIO(), **(self.options | kwargs))

    def test_dry_run_does_not_write(self):
        self.run_bind()
        self.assertFalse(Connection.objects.exists())

    def test_apply_is_idempotent_and_disabled(self):
        self.run_bind(apply=True)
        self.run_bind(apply=True)
        self.assertEqual(Connection.objects.count(), 1)
        conn = Connection.objects.get()
        self.assertEqual(conn.tenant_id, self.tenant.pk)
        self.assertFalse(conn.enabled)

    def test_wrong_app_shop_id_rejected(self):
        with self.assertRaises(CommandError):
            self.run_bind(app_shop_id='vdd-other', apply=True)

    def test_foreign_tenant_rejected(self):
        other = Tenant.objects.create(slug='other', name='Other', whatsapp_number='5511999999922')
        Connection.objects.create(tenant=other, provider='99food', mode='test', merchant_id=self.options['shop_id'])
        with self.assertRaises(CommandError):
            self.run_bind(apply=True)

    def test_second_shop_rejected(self):
        Connection.objects.create(tenant=self.tenant, provider='99food', mode='test', merchant_id='123')
        with self.assertRaises(CommandError):
            self.run_bind(apply=True)
