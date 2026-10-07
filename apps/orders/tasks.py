from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.integrations.models import TenantWhatsAppAgent, TenantWhatsAppConversation
from apps.integrations.whatsapp.client import EvolutionError
from apps.integrations.whatsapp_agent.client import TenantEvolutionClient

from .models import OrderStatusNotification


def _skip_if_superseded(notice, now):
    event = notice.event
    order = event.order
    newer = order.status_events.filter(created_at__gt=event.created_at).exclude(
        to_status=event.to_status
    ).exists()
    if newer or order.status != event.to_status:
        notice.skipped_at = now
        notice.last_error = "Aviso substituído por um status mais recente."
        notice.save(update_fields=["skipped_at", "last_error"])
        return True
    return False


@shared_task(soft_time_limit=45, time_limit=60)
def deliver_order_status_notification(notification_id):
    if not getattr(settings, "WHATSAPP_AGENT_ENABLED", False):
        return "disabled"

    with transaction.atomic():
        notice = (
            OrderStatusNotification.objects.select_for_update()
            .select_related("event__order", "tenant")
            .filter(pk=notification_id)
            .first()
        )
        if notice is None:
            return "missing"
        if notice.sent_at:
            return "sent"
        if notice.skipped_at:
            return "skipped"
        now = timezone.now()
        if _skip_if_superseded(notice, now):
            return "superseded"
        # Avoid concurrent workers and immediate repeats after a provider timeout.
        if notice.attempted_at and (now - notice.attempted_at).total_seconds() < 90:
            return "recent-attempt"

        agent = TenantWhatsAppAgent.objects.filter(
            tenant=notice.tenant,
            instance_created=True,
            status=TenantWhatsAppAgent.Status.OPEN,
        ).first()
        if agent is None:
            notice.last_error = "WhatsApp da loja não está conectado."
            notice.save(update_fields=["last_error"])
            return "offline"

        notice.attempts += 1
        notice.attempted_at = now
        notice.last_error = ""
        notice.save(update_fields=["attempts", "attempted_at", "last_error"])
        instance_name = agent.instance_name
        recipient = notice.recipient
        text = notice.text

    # External write happens outside the row lock. ``attempted_at`` prevents two
    # workers from firing the same notice at once.
    try:
        message_id = TenantEvolutionClient().send_text(instance_name, recipient, text)
    except EvolutionError as exc:
        OrderStatusNotification.objects.filter(pk=notification_id, sent_at__isnull=True).update(
            last_error=f"Falha de envio: {exc.reason}"[:160]
        )
        return "send-error"

    now = timezone.now()
    OrderStatusNotification.objects.filter(pk=notification_id, sent_at__isnull=True).update(
        sent_at=now,
        last_error="",
    )
    TenantWhatsAppConversation.objects.filter(
        tenant=notice.tenant, phone_number=recipient
    ).update(last_agent_message_at=now)
    return "sent"


@shared_task(soft_time_limit=60, time_limit=90)
def deliver_order_status_notifications():
    ids = list(
        OrderStatusNotification.objects.filter(
            sent_at__isnull=True,
            skipped_at__isnull=True,
        )
        .order_by("created_at", "pk")
        .values_list("pk", flat=True)[:50]
    )
    results = {"sent": 0, "skipped": 0, "pending": 0}
    for pk in ids:
        result = deliver_order_status_notification(pk)
        if result == "sent":
            results["sent"] += 1
        elif result in {"skipped", "superseded"}:
            results["skipped"] += 1
        else:
            results["pending"] += 1
    return results
