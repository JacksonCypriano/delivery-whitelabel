from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Category, Product
from apps.tenants.choices import FulfillmentMode
from apps.tenants.models import DeliveryZone, Tenant


class CriticalTestCase(TestCase):
    password = "SenhaForte!2026"

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(name="Loja Alpha", slug="alpha", whatsapp_number="5511999990001", fulfillment_mode=FulfillmentMode.DELIVERY_AND_PICKUP, pickup_address="Rua Alpha", pickup_number="10", pickup_neighborhood="Centro", pickup_city="São Paulo", pickup_zip_code="01001-000")
        cls.tenant_b = Tenant.objects.create(name="Loja Beta", slug="beta", whatsapp_number="5511999990002", fulfillment_mode=FulfillmentMode.DELIVERY_AND_PICKUP, pickup_address="Rua Beta", pickup_number="20", pickup_neighborhood="Centro", pickup_city="São Paulo", pickup_zip_code="01002-000")

        cls.category_a = Category.objects.create(tenant=cls.tenant_a, name="Lanches")
        cls.category_b = Category.objects.create(tenant=cls.tenant_b, name="Lanches")
        cls.product_a = Product.objects.create(tenant=cls.tenant_a, category=cls.category_a, name="Produto Alpha", price=Decimal("20.00"))
        cls.product_b = Product.objects.create(tenant=cls.tenant_b, category=cls.category_b, name="Produto Beta", price=Decimal("30.00"))

        cls.zone_a = DeliveryZone.objects.create(tenant=cls.tenant_a, city="São Paulo", neighborhood="Vila Mariana", fee=Decimal("7.50"))
        cls.zone_b = DeliveryZone.objects.create(tenant=cls.tenant_b, city="São Paulo", neighborhood="Moema", fee=Decimal("9.00"))

        User = get_user_model()
        cls.admin_a = User.objects.create_user(username="admin_alpha", password=cls.password, tenant=cls.tenant_a, is_tenant_admin=True, is_staff=True)
        cls.admin_b = User.objects.create_user(username="admin_beta", password=cls.password, tenant=cls.tenant_b, is_tenant_admin=True, is_staff=True)
        cls.superuser = User.objects.create_superuser(username="root_test", email="root@example.com", password=cls.password)

    def host(self, tenant):
        return f"{tenant.slug}.lvh.me"
