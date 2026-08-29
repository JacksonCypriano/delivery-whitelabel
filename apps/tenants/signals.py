from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from apps.marketplace.models import MarketplaceProfile
from apps.stores.models import Product
from apps.tenants.models import BrandConfig, BusinessHour, DeliveryZone, Tenant

from .onboarding import enforce_store_listing


def _tenant_id(instance):
    return getattr(instance, "tenant_id", None) or getattr(instance, "pk", None)


@receiver(post_save, sender=Tenant)
def tenant_configuration_changed(sender, instance, **kwargs):
    enforce_store_listing(instance.pk)


@receiver([post_save, post_delete], sender=BrandConfig)
@receiver([post_save, post_delete], sender=BusinessHour)
@receiver([post_save, post_delete], sender=DeliveryZone)
@receiver([post_save, post_delete], sender=Product)
def related_configuration_changed(sender, instance, **kwargs):
    tenant_id = getattr(instance, "tenant_id", None)
    if tenant_id:
        enforce_store_listing(tenant_id)


@receiver(m2m_changed, sender=MarketplaceProfile.categories.through)
def marketplace_categories_changed(sender, instance, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        enforce_store_listing(instance.tenant_id)
