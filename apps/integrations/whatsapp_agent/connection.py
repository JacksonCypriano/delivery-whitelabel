import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.integrations.models import TenantWhatsAppAgent, TenantWhatsAppAgentEvent
from apps.integrations.whatsapp.client import EvolutionError

from .client import TenantEvolutionClient
from .provider import extract_qr


BACKOFF_SECONDS = (60, 180, 600)
RECONNECT_CYCLE_COOLDOWN_SECONDS = 1800
REASONS = {
    "configuration": "Configuração do agente/Evolution incompleta.",
    "credentials": "Credencial recusada pela Evolution.",
    "not_found": "Instância não encontrada na Evolution.",
    "rate_limit": "Limite de requisições da Evolution atingido.",
    "unavailable": "Evolution indisponível ou sem resposta válida.",
    "invalid_response": "Resposta inesperada da Evolution.",
}


def feature_enabled():
    return bool(settings.WHATSAPP_AGENT_ENABLED)


def instance_name_for(tenant):
    # Evolution accepts a conservative lowercase alphanumeric identifier.
    suffix = re.sub(r"[^a-z0-9]", "", tenant.slug.lower())[:32]
    return f"vddtenant{tenant.pk}{suffix}"[:100]


def get_or_create_agent(tenant):
    agent, _ = TenantWhatsAppAgent.objects.get_or_create(
        tenant=tenant,
        defaults={"instance_name": instance_name_for(tenant)},
    )
    return agent


def add_event(agent, kind, description):
    TenantWhatsAppAgentEvent.objects.create(
        agent=agent, kind=kind[:40], description=description[:200]
    )


def _save_open(agent, now=None):
    now = now or timezone.now()
    changed = agent.status != TenantWhatsAppAgent.Status.OPEN
    agent.status = TenantWhatsAppAgent.Status.OPEN
    agent.instance_created = True
    agent.requires_pairing = False
    agent.reconnect_attempts = 0
    agent.next_reconnect_at = None
    agent.checked_at = now
    agent.connected_at = now
    agent.last_error = ""
    agent.save()
    if changed:
        add_event(agent, "connected", "WhatsApp conectado.")


def _save_not_open(agent, status, reason="", now=None):
    now = now or timezone.now()
    changed = agent.status != status
    agent.status = status
    agent.checked_at = now
    agent.disconnected_at = now
    agent.last_error = REASONS.get(reason, reason)[:160]
    agent.save()
    if changed:
        add_event(agent, "state_changed", f"Situação: {agent.get_status_display()}.")


def refresh_agent(agent, client=None):
    if not feature_enabled():
        raise EvolutionError("configuration")
    client = client or TenantEvolutionClient()
    try:
        status = client.status(agent.instance_name)
    except EvolutionError as exc:
        if exc.reason == "not_found":
            agent.instance_created = False
        _save_not_open(agent, TenantWhatsAppAgent.Status.ERROR, exc.reason)
        return agent
    agent.instance_created = True
    if status == "open":
        _save_open(agent)
    else:
        _save_not_open(agent, status)
    return agent


def connect_agent(agent, client=None):
    if not feature_enabled():
        raise EvolutionError("configuration")
    client = client or TenantEvolutionClient()

    # Always probe first. This recovers cleanly if the Django row was recreated
    # while the corresponding Evolution instance still exists.
    try:
        current = client.status(agent.instance_name)
        agent.instance_created = True
        client.set_agent_settings(agent.instance_name)
        if current == "open":
            _save_open(agent)
            return None
        agent.save(update_fields=("instance_created", "updated_at"))
    except EvolutionError as exc:
        if exc.reason != "not_found":
            raise
        agent.instance_created = False
        agent.save(update_fields=("instance_created", "updated_at"))

    if not agent.instance_created:
        data = client.create(agent.instance_name)
        agent.instance_created = True
        agent.status = TenantWhatsAppAgent.Status.PAIRING
        agent.requires_pairing = True
        agent.checked_at = timezone.now()
        agent.last_error = ""
        agent.save()
        add_event(agent, "instance_created", "Instância criada; aguardando pareamento.")
        qr = extract_qr(data)
        if qr:
            return qr

    data = client.connect(agent.instance_name)
    qr = extract_qr(data)
    agent.status = TenantWhatsAppAgent.Status.PAIRING
    agent.requires_pairing = True
    agent.checked_at = timezone.now()
    agent.save()
    add_event(agent, "pairing", "Novo QR Code de pareamento solicitado.")
    if not qr:
        raise EvolutionError("invalid_response")
    return qr


def disconnect_agent(agent, client=None):
    if not feature_enabled():
        raise EvolutionError("configuration")
    client = client or TenantEvolutionClient()
    provider_error = None
    try:
        client.logout(agent.instance_name)
    except EvolutionError as exc:
        provider_error = exc
        try:
            state = client.status(agent.instance_name)
        except EvolutionError:
            raise provider_error
        if state != "close":
            raise provider_error

    now = timezone.now()
    agent.instance_created = True
    agent.status = TenantWhatsAppAgent.Status.PAIRING
    agent.requires_pairing = True
    agent.reconnect_attempts = 0
    agent.next_reconnect_at = None
    agent.checked_at = now
    agent.disconnected_at = now
    agent.last_error = "WhatsApp desconectado pela loja; faça um novo pareamento."
    agent.save()
    if provider_error:
        add_event(
            agent,
            "logout_confirmed",
            "A Evolution retornou erro no logout, mas a instância foi confirmada como desconectada.",
        )
    else:
        add_event(agent, "logout", "WhatsApp desconectado pela loja; novo pareamento necessário.")
    return agent


def apply_connection_webhook(agent, data):
    now = timezone.now()
    state = str(data.get("state") or "")
    reason = str(data.get("statusReason") or "")
    agent.webhook_at = now
    agent.instance_created = True
    if state == "open":
        was_open = agent.status == TenantWhatsAppAgent.Status.OPEN
        agent.status = TenantWhatsAppAgent.Status.OPEN
        agent.requires_pairing = False
        agent.reconnect_attempts = 0
        agent.next_reconnect_at = None
        agent.checked_at = now
        agent.connected_at = now
        agent.last_error = ""
        agent.save()
        if not was_open:
            add_event(agent, "connected", "WhatsApp conectado.")
        return
    if state not in {"close", "connecting"}:
        return
    agent.status = state
    agent.checked_at = now
    agent.disconnected_at = now
    if state == "close" and reason == "401":
        agent.status = TenantWhatsAppAgent.Status.PAIRING
        agent.requires_pairing = True
        agent.next_reconnect_at = None
        agent.last_error = "A sessão foi invalidada; faça um novo pareamento."
        add_event(agent, "pairing_required", "Sessão invalidada; novo pareamento necessário.")
    elif state == "close" and not agent.requires_pairing:
        agent.next_reconnect_at = now
        add_event(agent, "disconnected", "Conexão perdida; recuperação automática agendada.")
    agent.save()


def mark_pairing_hint(agent):
    agent.webhook_at = timezone.now()
    if agent.status != TenantWhatsAppAgent.Status.OPEN:
        agent.status = TenantWhatsAppAgent.Status.PAIRING
        agent.requires_pairing = True
    agent.save()


def monitor_agent(agent, client=None):
    if not feature_enabled():
        return agent
    client = client or TenantEvolutionClient()
    now = timezone.now()
    try:
        state = client.status(agent.instance_name)
        agent.instance_created = True
    except EvolutionError as exc:
        if exc.reason == "not_found":
            agent.instance_created = False
            agent.requires_pairing = True
        _save_not_open(agent, TenantWhatsAppAgent.Status.ERROR, exc.reason, now)
        return agent

    if state == "open":
        _save_open(agent, now)
        return agent

    _save_not_open(agent, state, now=now)
    if (
        state != "close"
        or agent.requires_pairing
        or not settings.WHATSAPP_AGENT_AUTO_RECONNECT
    ):
        return agent

    due = not agent.next_reconnect_at or agent.next_reconnect_at <= now
    maximum = max(1, int(settings.WHATSAPP_AGENT_MAX_RECONNECT_ATTEMPTS))
    if not due:
        return agent
    if agent.reconnect_attempts >= maximum:
        # Do not give up forever after one bad network window. Start a fresh,
        # rate-limited recovery cycle later without hammering the provider.
        agent.reconnect_attempts = 0
        agent.next_reconnect_at = now + timedelta(seconds=RECONNECT_CYCLE_COOLDOWN_SECONDS)
        agent.save(update_fields=("reconnect_attempts", "next_reconnect_at", "updated_at"))
        add_event(agent, "auto_reconnect_backoff", "Reconexão será tentada novamente após o período de espera.")
        return agent

    attempt = agent.reconnect_attempts + 1
    delay = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
    # Persist the budget before the external write; an ambiguous timeout must
    # never create an unbounded restart loop.
    with transaction.atomic():
        locked = TenantWhatsAppAgent.objects.select_for_update().get(pk=agent.pk)
        if locked.requires_pairing or locked.status == TenantWhatsAppAgent.Status.OPEN:
            return locked
        locked.reconnect_attempts = attempt
        locked.next_reconnect_at = now + timedelta(seconds=delay)
        locked.save()
        agent = locked
    try:
        client.restart(agent.instance_name)
        agent.status = TenantWhatsAppAgent.Status.CONNECTING
        agent.last_error = ""
        agent.save()
        add_event(agent, "auto_reconnect", f"Reconexão automática {attempt}/{maximum} solicitada.")
    except EvolutionError as exc:
        agent.status = TenantWhatsAppAgent.Status.ERROR
        agent.last_error = REASONS.get(exc.reason, "Falha ao solicitar reconexão.")
        if exc.reason == "not_found":
            agent.instance_created = False
            agent.requires_pairing = True
        agent.save()
        add_event(agent, "auto_reconnect_error", f"Reconexão automática {attempt}/{maximum} não confirmada.")
    return agent
