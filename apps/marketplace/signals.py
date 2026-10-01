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


# Invoice.status reaches PAID only after billing.services.apply_payment validates
# the remote Asaas object and the credit transaction. This hook never calls Google.
@receiver(post_save, sender="billing.Invoice")
def capture_marketing_first_payment(sender, instance, raw=False, **kwargs):
    if (raw or instance.environment != "production" or instance.months <= 0
            or instance.additional_service_id is not None):
        return
    from django.db import transaction
    from .acquisition import record_first_payment, record_invoice_created, reflect_payment_review
    import logging

    def after_commit():
        try:
            record_invoice_created(instance)
            reflect_payment_review(instance)
            if instance.status == "PAID":
                record_first_payment(instance)
        except Exception:
            logging.getLogger(__name__).exception("Não foi possível registrar a etapa de aquisição")

    transaction.on_commit(after_commit)
