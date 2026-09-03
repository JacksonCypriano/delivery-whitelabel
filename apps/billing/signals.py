from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.tenants.models import Tenant
from .models import Subscription


@receiver(post_save, sender=Tenant)
def new_store_subscription(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    enabled = settings.BILLING_ENABLED
    Subscription.objects.get_or_create(
        tenant=instance,
        defaults={
            "managed": enabled,
            "billing_suspended": enabled,
            "manually_blocked": False if enabled else not instance.is_active,
        },
    )
    if enabled:
        Tenant.objects.filter(pk=instance.pk).update(is_active=False)
        instance.is_active = False
