import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.integrations.models import TenantWhatsAppConversation
from apps.orders.models import Order
from apps.orders.whatsapp_marker import extract_order_id


def conversation(tenant, phone):
    return TenantWhatsAppConversation.objects.get_or_create(
        tenant=tenant, phone_number=phone
    )[0]


def active_context(row, now=None):
    """Return short conversation context, expiring it after inactivity."""
    now = now or timezone.now()
    timeout = timedelta(
        minutes=max(1, int(settings.WHATSAPP_AGENT_CONTEXT_TIMEOUT_MINUTES))
    )
    reference = row.context_updated_at or row.last_customer_message_at
    if not reference or now - reference > timeout:
        if row.context or row.context_updated_at:
            row.context = {}
            row.context_updated_at = None
            row.save(update_fields=("context", "context_updated_at", "updated_at"))
        return {}
    return row.context if isinstance(row.context, dict) else {}


def update_context(row, context, now=None):
    now = now or timezone.now()
    row.context = context if isinstance(context, dict) else {}
    row.context_updated_at = now if row.context else None
    row.save(update_fields=("context", "context_updated_at", "updated_at"))
    return row


def clear_context(row):
    if row.context or row.context_updated_at:
        row.context = {}
        row.context_updated_at = None
        row.save(update_fields=("context", "context_updated_at", "updated_at"))
    return row


def pause(tenant, phone, minutes, reason):
    row = conversation(tenant, phone)
    until = timezone.now() + timedelta(minutes=max(1, int(minutes)))
    if not row.ai_paused_until or row.ai_paused_until < until:
        row.ai_paused_until = until
    row.pause_reason = reason
    if reason == TenantWhatsAppConversation.PauseReason.MANUAL:
        row.last_store_message_at = timezone.now()
    row.context = {}
    row.context_updated_at = None
    row.save()
    return row


def pause_for_manual_store_message(tenant, phone):
    return pause(
        tenant,
        phone,
        settings.WHATSAPP_AGENT_MANUAL_PAUSE_MINUTES,
        TenantWhatsAppConversation.PauseReason.MANUAL,
    )


def validate_order_marker(tenant, phone, text):
    order_id = extract_order_id(text)
    if not order_id:
        return None
    order = (
        Order.objects.filter(
            pk=order_id,
            tenant=tenant,
            whatsapp_opened_at__isnull=False,
            abandoned_at__isnull=True,
        )
        .only("id", "customer_phone")
        .first()
    )
    if not order:
        return None
    order_phone = re.sub(r"\D", "", order.customer_phone or "")
    sender = re.sub(r"\D", "", phone or "")
    # Customer checkout may contain local DDD format while Evolution returns 55...
    if order_phone and not (sender.endswith(order_phone) or order_phone.endswith(sender)):
        return None
    return order


def pause_for_order(tenant, phone):
    return pause(
        tenant,
        phone,
        settings.WHATSAPP_AGENT_ORDER_PAUSE_MINUTES,
        TenantWhatsAppConversation.PauseReason.ORDER,
    )
