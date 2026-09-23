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


@shared_task(soft_time_limit=120, time_limit=150)
def monitor_tenant_whatsapp_agents():
    if not getattr(settings, "WHATSAPP_AGENT_ENABLED", False):
        return "disabled"
    from .models import TenantWhatsAppAgent
    from .whatsapp_agent.connection import monitor_agent

    checked = 0
    for agent in (
        TenantWhatsAppAgent.objects.filter(tenant__is_active=True, instance_created=True)
        .select_related("tenant")
        .order_by("pk")[:500]
    ):
        try:
            monitor_agent(agent)
            checked += 1
        except Exception:
            log.exception("Falha isolada ao monitorar agente WhatsApp tenant_id=%s", agent.tenant_id)
    return f"checked={checked}"


@shared_task(soft_time_limit=45, time_limit=60)
def process_tenant_whatsapp_message(agent_id, message_id, phone, text, message_kind="text"):
    if not getattr(settings, "WHATSAPP_AGENT_ENABLED", False):
        return "disabled"

    from .models import TenantWhatsAppAgent, TenantWhatsAppConversation
    from .whatsapp.client import EvolutionError
    from .whatsapp_agent.agent import answer
    from .whatsapp_agent.client import TenantEvolutionClient
    from .whatsapp_agent.connection import add_event
    from .whatsapp_agent.conversations import (
        active_context,
        conversation,
        pause,
        pause_for_order,
        update_context,
        validate_order_marker,
    )
    from .whatsapp_agent.provider import mark_outbound_message, mark_outbound_pending

    try:
        agent = TenantWhatsAppAgent.objects.select_related("tenant").get(
            pk=agent_id, tenant__is_active=True
        )
    except TenantWhatsAppAgent.DoesNotExist:
        return "missing-agent"

    row = conversation(agent.tenant, phone)
    now = timezone.now()
    context = active_context(row, now=now)
    row.last_customer_message_at = now
    row.save(update_fields=("last_customer_message_at", "updated_at"))

    order = validate_order_marker(agent.tenant, phone, text)
    if order:
        pause_for_order(agent.tenant, phone)
        add_event(agent, "order_ignored", f"Pedido #{order.pk} recebido; agente pausado para a loja assumir.")
        return "order-ignored"

    if not agent.ai_enabled:
        return "agent-disabled"

    row.refresh_from_db()
    if row.ai_paused_until and row.ai_paused_until > now:
        return "conversation-paused"

    if message_kind in {"audio", "image", "video", "document", "sticker", "location", "contact"}:
        media_replies = {
            "audio": (
                "audio",
                "Ainda não consigo interpretar mensagens de áudio 🎧\n\n"
                "Por enquanto, me envie sua dúvida por *texto* que eu te ajudo por aqui 😊",
            ),
            "location": (
                "location",
                "Ainda não consigo usar a localização compartilhada diretamente 📍\n\n"
                "Me envie por *texto* a cidade e o bairro que eu consulto a entrega para você 😊",
            ),
            "image": (
                "media",
                "Ainda não consigo interpretar imagens por aqui 🖼️\n\n"
                "Me envie por *texto* o nome do produto ou a sua dúvida que eu te ajudo 😊",
            ),
            "video": (
                "media",
                "Ainda não consigo interpretar vídeos por aqui 🎥\n\n"
                "Me envie sua dúvida por *texto* que eu te ajudo 😊",
            ),
            "document": (
                "media",
                "Ainda não consigo interpretar documentos enviados pelo WhatsApp 📄\n\n"
                "Me envie sua dúvida por *texto* que eu te ajudo 😊",
            ),
            "sticker": (
                "media",
                "Ainda não consigo interpretar figurinhas 😊\n\n"
                "Se precisar de ajuda, me envie uma mensagem por *texto*.",
            ),
            "contact": (
                "media",
                "Ainda não consigo interpretar contatos compartilhados pelo WhatsApp.\n\n"
                "Me envie sua dúvida por *texto* que eu te ajudo 😊",
            ),
        }
        reply_intent, reply_text = media_replies[message_kind]
        reply_context = {"intent": reply_intent}
        reply_pause_minutes = 0
        reply_pause_reason = ""
    else:
        reply = answer(agent.tenant, text, context=context)
        if not reply.text:
            return "no-reply"
        reply_text = reply.text
        reply_intent = reply.intent
        reply_context = reply.context
        reply_pause_minutes = reply.pause_minutes
        reply_pause_reason = reply.pause_reason

    client = TenantEvolutionClient()
    mark_outbound_pending(agent.instance_name, phone, reply_text)
    try:
        provider_message_id = client.send_text(agent.instance_name, phone, reply_text)
    except EvolutionError as exc:
        agent.last_error = f"Falha ao responder mensagem: {exc.reason}"[:160]
        agent.save(update_fields=("last_error", "updated_at"))
        add_event(agent, "reply_error", "Não foi possível enviar uma resposta automática.")
        return "send-error"

    mark_outbound_message(agent.instance_name, provider_message_id)
    row.last_agent_message_at = timezone.now()
    row.save(update_fields=("last_agent_message_at", "updated_at"))
    update_context(row, reply_context)

    if reply_pause_minutes:
        reason = reply_pause_reason or TenantWhatsAppConversation.PauseReason.HUMAN
        pause(agent.tenant, phone, reply_pause_minutes, reason)

    add_event(agent, "answered", f"Resposta automática enviada ({reply_intent}).")
    return f"answered:{reply_intent}"
