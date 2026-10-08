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


GROUP_PRIVATE_NOTICE = (
    "Oi! 😊 O atendimento automático funciona apenas em conversa privada.\n\n"
    "Me chama no privado que eu te ajudo por lá."
)


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
def notify_tenant_whatsapp_group_once(agent_id, group_jid):
    if not getattr(settings, "WHATSAPP_AGENT_ENABLED", False):
        return "disabled"

    from .models import TenantWhatsAppAgent, TenantWhatsAppGroupNotice
    from .whatsapp.client import EvolutionError
    from .whatsapp_agent.client import TenantEvolutionClient
    from .whatsapp_agent.connection import add_event

    try:
        agent = TenantWhatsAppAgent.objects.select_related("tenant").get(
            pk=agent_id, tenant__is_active=True
        )
    except TenantWhatsAppAgent.DoesNotExist:
        return "missing-agent"

    if not agent.ai_enabled:
        return "agent-disabled"
    if not str(group_jid or "").endswith("@g.us"):
        return "invalid-group"

    notice, created = TenantWhatsAppGroupNotice.objects.get_or_create(
        tenant=agent.tenant,
        group_jid=str(group_jid)[:160],
    )
    if not created:
        return "already-notified"

    try:
        TenantEvolutionClient().send_text(
            agent.instance_name,
            notice.group_jid,
            GROUP_PRIVATE_NOTICE,
        )
    except EvolutionError:
        add_event(
            agent,
            "group_notice_error",
            "Primeiro aviso do grupo não pôde ser confirmado; novas mensagens do grupo continuarão silenciosas.",
        )
        return "send-error"

    notice.sent_at = timezone.now()
    notice.save(update_fields=("sent_at",))
    add_event(agent, "group_notice", "Grupo orientado uma única vez a continuar o atendimento no privado.")
    return "notified"


@shared_task(soft_time_limit=45, time_limit=60)
def process_tenant_whatsapp_message(agent_id, message_id, phone, text, message_kind="text"):
    if not getattr(settings, "WHATSAPP_AGENT_ENABLED", False):
        return "disabled"

    from .models import TenantWhatsAppAgent, TenantWhatsAppConversation
    from .whatsapp.client import EvolutionError
    from .whatsapp_agent.agent import answer, format_whatsapp_text
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
    from .models import ConversationEntry
    _, first_delivery = ConversationEntry.objects.get_or_create(conversation=row,key="in:"+message_id,defaults={"role":"customer","text":text[:4000] or "["+message_kind+"]"})
    if not first_delivery:
        return "duplicate-message"
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

    media_image = message_kind == "image"
    if message_kind in {"audio", "image"} and getattr(settings, "WHATSAPP_MEDIA_ENABLED", False):
        from .whatsapp_agent.media import interpret, MediaUnavailable
        try:
            text = interpret(agent, message_id, phone, message_kind)
            ConversationEntry.objects.get_or_create(conversation=row,key="media:"+message_id,defaults={"role":"transcript","text":text})
            message_kind = "text"
        except MediaUnavailable:
            pause(agent.tenant, phone, 60, TenantWhatsAppConversation.PauseReason.HUMAN)
            add_event(agent,"media_handoff","Mídia encaminhada para atendimento humano; sem confirmação financeira.")
            return "media-handoff"
    checkout_reply = None
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
        from .whatsapp_agent.checkout import handle_checkout
        checkout_reply = handle_checkout(agent.tenant, phone, message_id, text) if getattr(settings, "WHATSAPP_AGENT_CHECKOUT_ENABLED", True) and not media_image else None
        reply = checkout_reply or answer(agent.tenant, text, context=context, phone=phone)
        if not reply.text:
            return "no-reply"
        reply_text = reply.text
        reply_intent = reply.intent
        reply_context = reply.context
        reply_pause_minutes = reply.pause_minutes
        reply_pause_reason = reply.pause_reason

    row.refresh_from_db()
    if row.is_paused:
        return "conversation-paused"
    reply_text = format_whatsapp_text(reply_text)
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
    if checkout_reply:
        if checkout_reply.choices and getattr(settings, "WHATSAPP_AGENT_BUTTONS_ENABLED", True):
            mark_outbound_pending(agent.instance_name, phone, "Escolha uma opção")
            mark_outbound_pending(agent.instance_name, phone, "Opções do pedido")
            try:
                button_id = client.send_choices(agent.instance_name, phone, checkout_reply.choices)
                mark_outbound_message(agent.instance_name, button_id)
            except EvolutionError:
                pass  # The complete numbered text was already sent.
        if checkout_reply.pix_checkout_id:
            send_checkout_pix(checkout_reply.pix_checkout_id)
    row.last_agent_message_at = timezone.now()
    row.save(update_fields=("last_agent_message_at", "updated_at"))
    ConversationEntry.objects.get_or_create(conversation=row,key="out:"+message_id,defaults={"role":"agent","text":reply_text})
    if reply_pause_minutes:
        ConversationEntry.objects.get_or_create(conversation=row,key="handoff-context:"+message_id,defaults={"role":"handoff","text":reply_pause_reason,"context":context})
    update_context(row, reply_context)

    if reply_pause_minutes:
        reason = reply_pause_reason or TenantWhatsAppConversation.PauseReason.HUMAN
        pause(agent.tenant, phone, reply_pause_minutes, reason)

    add_event(agent, "answered", f"Resposta automática enviada ({reply_intent}).")
    return f"answered:{reply_intent}"


@shared_task(soft_time_limit=90, time_limit=120)
def send_checkout_pix(checkout_id):
    from apps.billing.provider import BillingError
    from .models import WhatsAppCheckout, TenantWhatsAppAgent
    from .whatsapp_agent.checkout_payments import issue_pix
    from .whatsapp_agent.client import TenantEvolutionClient
    from .whatsapp_agent.provider import mark_outbound_message, mark_outbound_pending
    from .whatsapp.client import EvolutionError
    c = WhatsAppCheckout.objects.select_related("conversation", "cart").get(pk=checkout_id)
    agent = TenantWhatsAppAgent.objects.get(tenant_id=c.cart.tenant_id)
    client = TenantEvolutionClient()
    phone = c.conversation.phone_number
    try:
        qr = issue_pix(checkout_id)
        if qr is None:
            return "not-pending"
        # Copy/paste is its own message, without formatting or an appended caption.
        mark_outbound_pending(agent.instance_name, phone, qr["payload"])
        mid = client.send_text(agent.instance_name, phone, qr["payload"])
        mark_outbound_message(agent.instance_name, mid)
        mark_outbound_pending(agent.instance_name, phone, "Pix do seu pedido — aguardando pagamento")
        try:
            mid = client.send_pix_image(agent.instance_name, phone, qr["encodedImage"])
            mark_outbound_message(agent.instance_name, mid)
        except EvolutionError:
            return "copy-paste-sent"
        return "pix-sent"
    except (BillingError, ValueError):
        text = "Ainda não consegui recuperar seu Pix. Seu carrinho está salvo e não vou criar uma cobrança duplicada.\n\nTente *Pix* novamente em instantes ou escreva *atendente*."
        mark_outbound_pending(agent.instance_name, phone, text)
        try:
            mid = client.send_text(agent.instance_name, phone, text)
            mark_outbound_message(agent.instance_name, mid)
        except EvolutionError:
            pass
        return "pix-pending"
    except EvolutionError:
        return "send-error"


@shared_task(soft_time_limit=90, time_limit=120)
def deliver_whatsapp_order_notices():
    from django.db import transaction
    from .models import WhatsAppOrderNotice, TenantWhatsAppAgent
    from .whatsapp_agent.client import TenantEvolutionClient
    from .whatsapp_agent.provider import mark_outbound_message, mark_outbound_pending
    from .whatsapp.client import EvolutionError
    if not getattr(settings, "WHATSAPP_AGENT_ENABLED", False):
        return "disabled"
    for pk in WhatsAppOrderNotice.objects.filter(sent_at__isnull=True).order_by("pk").values_list("pk", flat=True)[:20]:
        with transaction.atomic():
            notice = WhatsAppOrderNotice.objects.select_for_update(of=("self",)).select_related("checkout__cart").get(pk=pk)
            if notice.sent_at:
                continue
            agent = TenantWhatsAppAgent.objects.filter(tenant_id=notice.checkout.cart.tenant_id, instance_created=True).first()
            if not agent:
                continue
            mark_outbound_pending(agent.instance_name, notice.recipient, notice.text)
            try:
                mid = TenantEvolutionClient().send_text(agent.instance_name, notice.recipient, notice.text)
            except EvolutionError:
                continue
            mark_outbound_message(agent.instance_name, mid)
            notice.sent_at = timezone.now()
            notice.save(update_fields=["sent_at"])
    return "processed"


@shared_task(soft_time_limit=90, time_limit=120)
def maintain_whatsapp_checkouts():
    """Recover uncertain issuance and cancel unpaid charges after 30 minutes.

    Never infer non-payment from a timeout and never release stock until Asaas
    acknowledges deletion. Paid orders still require the persisted webhook.
    """
    from datetime import timedelta
    from django.db import transaction
    from apps.billing.provider import BillingError, environment
    from .models import WhatsAppCheckout
    from .whatsapp_agent.checkout_payments import issue_pix, cancel_payment
    ids = list(WhatsAppCheckout.objects.filter(status__in=["issuing", "uncertain", "pending"], environment=environment()).order_by("updated_at").values_list("pk", flat=True)[:10])
    for pk in ids:
        c = WhatsAppCheckout.objects.get(pk=pk)
        if not c.provider_id:
            try:
                issue_pix(pk)
            except (BillingError, ValueError):
                pass
        with transaction.atomic():
            c = WhatsAppCheckout.objects.select_for_update(of=("self",)).select_related("cart__tenant", "conversation").get(pk=pk)
            if c.status == "pending" and c.expires_at and c.expires_at <= timezone.now():
                cancel_payment(c)
            c.save(update_fields=["status", "data", "updated_at"])
