from datetime import time

from apps.marketplace.models import MarketplaceCategory, MarketplaceProfile
from apps.tenants.models import BrandConfig
from apps.tenants.onboarding import enforce_store_listing, get_store_setup

from .base import CriticalTestCase


class OnboardingCriticalTests(CriticalTestCase):
    def _complete_tenant(self, tenant, category):
        profile = MarketplaceProfile.objects.create(tenant=tenant, is_listed=False, short_description="Uma loja completa para testes", city="São Paulo", state="SP", neighborhood="Centro")
        marketplace_category = MarketplaceCategory.objects.create(name=f"Categoria {tenant.slug}")
        profile.categories.add(marketplace_category)
        BrandConfig.objects.create(tenant=tenant, logo="logos/test-logo.png")
        hour = tenant.business_hours.get(weekday=0)
        hour.is_closed = False
        hour.opening_time = time(9, 0)
        hour.closing_time = time(18, 0)
        hour.save()
        return profile

    def test_new_incomplete_store_is_not_ready(self):
        setup = get_store_setup(self.tenant_a)
        self.assertFalse(setup["complete"])
        self.assertLess(setup["percent"], 100)

    def test_complete_store_reaches_100_percent(self):
        self._complete_tenant(self.tenant_a, self.category_a)
        setup = get_store_setup(self.tenant_a)
        self.assertTrue(setup["complete"])
        self.assertEqual(setup["percent"], 100)

    def test_incomplete_listed_store_is_automatically_unlisted(self):
        profile = MarketplaceProfile.objects.create(tenant=self.tenant_a, is_listed=False)
        MarketplaceProfile.objects.filter(pk=profile.pk).update(is_listed=True)
        enforce_store_listing(self.tenant_a.pk)
        profile.refresh_from_db()
        self.assertFalse(profile.is_listed)
