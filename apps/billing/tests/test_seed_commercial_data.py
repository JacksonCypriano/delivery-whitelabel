from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from apps.billing.models import AdditionalService, BillingSettings, Plan
from apps.marketplace.models import MarketplaceCategory, MarketplaceProfile
from apps.tenants.models import Tenant


class SeedCommercialDataTests(TestCase):
    def test_seed_is_idempotent_normalizes_catalog_and_does_not_override_fees(self):
        policy = BillingSettings.current()
        policy.fixed_pix_fee = Decimal("9.99")
        policy.pix_enabled = False
        policy.boleto_enabled = True
        policy.card_enabled = True
        policy.save()

        Plan.objects.filter(months=1).update(name="Teste produção", monthly_price=5, discount=0)
        legacy = MarketplaceCategory.objects.create(name="Pizzarias", slug="pizzarias", icon="🍕")
        tenant = Tenant.objects.create(name="Loja", slug="loja-seed", whatsapp_number="5511999996666")
        profile = MarketplaceProfile.objects.get(tenant=tenant)
        profile.categories.add(legacy)

        call_command("seed_commercial_data", verbosity=0)
        call_command("seed_commercial_data", verbosity=0)

        monthly = Plan.objects.get(months=1)
        self.assertEqual(monthly.name, "Mensal")
        self.assertEqual(monthly.monthly_price, Decimal("199.00"))
        self.assertEqual(Plan.objects.filter(active=True, months__in=[1, 3, 6, 12]).count(), 4)
        self.assertEqual(AdditionalService.objects.filter(active=True).count(), 4)
        self.assertEqual(MarketplaceCategory.objects.filter(is_active=True, name="Pizzaria").count(), 1)
        legacy.refresh_from_db()
        self.assertFalse(legacy.is_active)
        self.assertTrue(profile.categories.filter(name="Pizzaria").exists())
        self.assertFalse(profile.categories.filter(name="Pizzarias").exists())

        policy.refresh_from_db()
        self.assertTrue(policy.pix_enabled)
        self.assertFalse(policy.boleto_enabled)
        self.assertFalse(policy.card_enabled)
        self.assertEqual(policy.fixed_pix_fee, Decimal("9.99"))
