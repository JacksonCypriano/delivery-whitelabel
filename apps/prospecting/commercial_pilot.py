"""Non-bypassable allowlist for the commercial WhatsApp pilot."""
import re
from django.conf import settings
from .commercial_models import CommercialPilotContact, CommercialHandoffAlert, CommercialOtpExclusion


def normalize_phone(value):
    """Accept Brazilian E.164 digits without spaces or a plus sign."""
    number = str(value or '').strip()
    if not re.fullmatch(r'55[1-9][0-9]{9,10}', number):
        raise ValueError('Informe número brasileiro com DDI 55 e DDD, somente dígitos.')
    if number == re.sub(r'\D', '', getattr(settings, 'MARKETING_WHATSAPP', '')):
        raise ValueError('O número comercial não pode ser contato do piloto.')
    return number


def eligible(phone, instance=None):
    """Fail closed: no allowlist entry means no automatic WhatsApp sending."""
    if not CommercialPilotContact.objects.filter(phone=phone, active=True).exists():
        return False
    if instance is None:
        # No instance means caller cannot prove OTP separation; deny.
        return False
    return not CommercialOtpExclusion.objects.filter(phone=phone, instance=instance).exists()


def alert_human(conversation, message, reason):
    # Conversation is row-locked by the receiving/processing code. One unresolved
    # handoff per thread, even if the provider replays an event.
    pending = CommercialHandoffAlert.objects.filter(
        conversation=conversation, state='pending',
    ).order_by('pk').first()
    if pending:
        return pending
    return CommercialHandoffAlert.objects.get_or_create(
        message=message,
        defaults={'conversation': conversation, 'reason': reason},
    )[0]


def human_replied(conversation):
    """Only a confirmed human reply (or explicitly audited external resolution) closes alerts.

    Taking ownership alone is not a reply; bot outbound must not invoke this.
    """
    from django.utils import timezone
    CommercialHandoffAlert.objects.filter(
        conversation=conversation, state='pending',
    ).update(state='resolved', acknowledged_at=timezone.now())


def otp_excluded(phone, instance):
    return CommercialOtpExclusion.objects.filter(phone=phone, instance=instance).exists()


def quarantine_otp_recipient(phone, instance):
    """Persist OTP suppression before outbound provider call (fail closed).

    Locks the commercial control to serialize against agent processing. Never
    retains the OTP content. Prior queued items are held, and existing chats
    are permanently paused pending separate manual support.
    """
    from django.db import transaction
    from django.utils import timezone
    from .commercial_models import CommercialControl, CommercialConversation, CommercialMessage
    from apps.integrations.whatsapp.service import normalize_br_phone
    normalized = normalize_br_phone(phone)
    with transaction.atomic():
        control = CommercialControl.objects.select_for_update().get(pk=1)
        if control.instance != instance:
            raise ValueError('otp_instance_mismatch')
        row, _ = CommercialOtpExclusion.objects.get_or_create(instance=instance, phone=normalized)
        CommercialOtpExclusion.objects.filter(pk=row.pk).update(last_otp_at=timezone.now())
        conversations = CommercialConversation.objects.select_for_update().filter(instance=instance, phone=normalized)
        ids = list(conversations.values_list('pk', flat=True))
        if ids:
            CommercialConversation.objects.filter(pk__in=ids).update(paused=True, reason='otp_only')
            CommercialMessage.objects.filter(conversation_id__in=ids, state='queued').update(state='held')
    return normalized
