import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import WhatsAppAlert
from .whatsapp.monitor import check_connection, enabled, identity

log = logging.getLogger(__name__)


@shared_task(soft_time_limit=60, time_limit=90)
def monitor_whatsapp():
    if not enabled():
        return
    try:
        check_connection()
    except Exception:
        log.error(
            "Monitoramento WhatsApp não concluído. Verifique banco e configuração."
        )


@shared_task(soft_time_limit=60, time_limit=90)
def send_whatsapp_alerts():
    if not enabled():
        return
    recipients = settings.EVOLUTION_ALERT_EMAILS
    try:
        if not recipients:
            return
        for recipient in recipients:
            validate_email(recipient)
    except ValidationError:
        log.error("Destinatários dos alertas WhatsApp inválidos.")
        return
    for pk in (
        WhatsAppAlert.objects.filter(state__identity=identity(), status="pending")
        .order_by("pk")
        .values_list("pk", flat=True)[:2]
    ):
        with transaction.atomic():
            alert = WhatsAppAlert.objects.select_for_update().get(pk=pk)
            if alert.status != "pending":
                continue
            alert.status = "sending"
            alert.attempted_at = timezone.now()
            alert.save()
            state = alert.state
            subject = (
                "WhatsApp recuperado"
                if alert.recovery
                else "WhatsApp indisponível — intervenção pode ser necessária"
            )
            body = (
                f"Ambiente: {state.environment}\n{subject}.\n"
                "Acesse Superadmin → Integrações da plataforma → Conexões WhatsApp / Evolution.\n"
                "O envio de OTP por WhatsApp pode ser afetado. Nenhuma ação de pareamento é automática.\n"
                "Este aviso corresponde a um incidente; consulte o painel para a situação atual."
            )
        try:
            count = EmailMessage(
                f"[VemDeDelivery] {subject}",
                body,
                settings.DEFAULT_FROM_EMAIL,
                recipients,
                connection=get_connection(timeout=15),
                headers={
                    "Message-ID": f"<vdd-whatsapp-{pk}-{alert.incident}@vemdedelivery.com.br>"
                },
            ).send()
            status = "sent" if count == 1 else "uncertain"
        except Exception:
            status = "uncertain"
        # SMTP may have accepted before a timeout. Don't spam with blind retries.
        WhatsAppAlert.objects.filter(pk=pk, status="sending").update(
            status=status, sent_at=timezone.now() if status == "sent" else None
        )
    WhatsAppAlert.objects.filter(
        state__identity=identity(),
        status="sending",
        attempted_at__lt=timezone.now() - timedelta(minutes=5),
    ).update(status="uncertain")
