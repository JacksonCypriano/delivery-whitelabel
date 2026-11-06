from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Order
from .realtime import publish_order_event


def _publish(order_id, tenant_id, event):
    transaction.on_commit(
        lambda: publish_order_event(order_id, tenant_id, event=event)
    )


@receiver(post_save, sender=Order)
def order_changed(sender, instance, created, **kwargs):
    _publish(
        instance.pk,
        instance.tenant_id,
        "order.created" if created else "order.updated",
    )


def connect_payment_signals():
    # Imported lazily from AppConfig.ready so app loading remains acyclic.
    from apps.billing.models import OrderPayment
    from apps.integrations.models import WhatsAppCheckout

    def payment_changed(sender, instance, **kwargs):
        if instance.order_id:
            _publish(instance.order_id, instance.tenant_id, "order.payment")

    def whatsapp_payment_changed(sender, instance, **kwargs):
        if instance.order_id:
            tenant_id = instance.cart.tenant_id
            _publish(instance.order_id, tenant_id, "order.payment")

    post_save.connect(
        payment_changed,
        sender=OrderPayment,
        dispatch_uid="orders.realtime.order_payment",
        weak=False,
    )
    post_save.connect(
        whatsapp_payment_changed,
        sender=WhatsAppCheckout,
        dispatch_uid="orders.realtime.whatsapp_checkout",
        weak=False,
    )
