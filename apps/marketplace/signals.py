from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.tenants.models import Tenant

from .models import MarketplaceProfile


@receiver(post_save, sender=Tenant)
def ensure_marketplace_profile(sender, instance, created, **kwargs):
    if not created:
        return

    MarketplaceProfile.objects.get_or_create(
        tenant=instance,
        defaults={
            "city": (instance.pickup_city or "").strip(),
            "neighborhood": (instance.pickup_neighborhood or "").strip(),
        },
    )
