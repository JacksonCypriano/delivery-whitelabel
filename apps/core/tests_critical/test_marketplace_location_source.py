from apps.marketplace.models import MarketplaceProfile
from apps.marketplace.views import _available_cities

from .base import CriticalTestCase


class MarketplaceLocationSourceCriticalTests(CriticalTestCase):
    def test_available_cities_uses_store_and_delivery_data_not_public_profile_location(self):
        self.tenant_a.pickup_city = "Osasco"
        self.tenant_a.save(update_fields=["pickup_city"])

        profile = MarketplaceProfile.objects.get(tenant=self.tenant_a)
        profile.city = ""
        profile.state = ""
        profile.neighborhood = ""
        profile.is_listed = True
        profile.save(update_fields=["city", "state", "neighborhood", "is_listed"])

        self.assertIn("Osasco", _available_cities())
