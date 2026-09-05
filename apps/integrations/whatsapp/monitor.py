"""One durable incident and lease per configured environment/instance.

Provider calls run outside transactions. Persist attempts before external writes:
an interrupted/ambiguous call must not reset the three-attempt budget.
"""

import hashlib
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.integrations.models import (
    WhatsAppAlert,
    WhatsAppIntegrationEvent,
    WhatsAppIntegrationState,
)
from .client import EvolutionClient, EvolutionError

BACKOFF = (60, 180, 600)
MAX_RESTART_ATTEMPTS = 3
REASONS = {
    "configuration": "Configuração incompleta ou inválida.",
    "credentials": "Credencial recusada pela Evolution.",
    "not_found": "Instância ou endpoint não encontrado.",
    "rate_limit": "Limite de requisições da Evolution atingido.",
    "unavailable": "Sem resposta válida da Evolution.",
    "invalid_response": "Resposta incompatível com a instância configurada.",
}


def enabled():
    return settings.EVOLUTION_MONITOR_ENABLED


def identity():
    return hashlib.sha256(
        "\0".join(
            (
                settings.EVOLUTION_MONITOR_ENVIRONMENT,
                settings.EVOLUTION_API_URL.rstrip("/"),
                settings.EVOLUTION_INSTANCE,
            )
        ).encode()
    ).hexdigest()


def current_state():
    return WhatsAppIntegrationState.objects.get_or_create(
        identity=identity(),
        defaults={
            "environment": settings.EVOLUTION_MONITOR_ENVIRONMENT,
            "instance": settings.EVOLUTION_INSTANCE[:100],
        },
    )[0]


def event(row, kind, description, actor=None):
    WhatsAppIntegrationEvent.objects.create(
        state=row,
        kind=kind,
        description=description,
        actor_id=actor,
        incident=row.incident,
    )


def claim():
    if not enabled():
        return None
    row = current_state()
    with transaction.atomic():
        row = WhatsAppIntegrationState.objects.select_for_update().get(pk=row.pk)
        now = timezone.now()
        if row.lease_until and row.lease_until > now:
            return None
        row.lease_token = uuid.uuid4()
        row.lease_until = now + timedelta(seconds=120)
        row.webhook_pending = False
        row.save()
        return row.pk, row.lease_token


def release(pk, token):
    WhatsAppIntegrationState.objects.filter(pk=pk, lease_token=token).update(
        lease_token=None, lease_until=None
    )


def locked(pk, token):
    return (
        WhatsAppIntegrationState.objects.select_for_update()
        .filter(pk=pk, lease_token=token, lease_until__gt=timezone.now())
        .first()
    )


def apply_observation(row, status, reason=""):
    now = timezone.now()
    previous = row.status
    # A gap in monitoring cannot count as continuously observed connectivity.
    if row.checked_at and now - row.checked_at > timedelta(minutes=3):
        row.online_since = None
    row.checked_at = now
    row.reason = REASONS.get(reason, "")
    if status == "open":
        row.observed_online_at = now
        row.pairing_hint_at = None
        row.online_since = row.online_since or now
        if row.incident and now - row.online_since >= timedelta(minutes=2):
            alerts = WhatsAppAlert.objects.filter(
                state=row, incident=row.incident, recovery=False
            )
            # Don't report recovery for an outage for which no email was attempted.
            if alerts.filter(status__in=("sending", "sent", "uncertain")).exists():
                WhatsAppAlert.objects.get_or_create(
                    state=row, incident=row.incident, recovery=True
                )
            alerts.filter(status="pending").update(status="skipped")
            event(row, "recovered", "Conexão recuperada e estável por dois minutos.")
            row.incident = None
            row.down_since = None
            row.attempts = 0
            row.next_attempt_at = None
            row.manual_required = False
        row.manual_requested = False
    else:
        row.online_since = None
        if not row.incident:
            row.incident = uuid.uuid4()
            row.down_since = now
            row.next_attempt_at = now + timedelta(seconds=BACKOFF[0])
            event(row, "outage", "Indisponibilidade detectada.")
        # A webhook is only a hint. Confirm not-open via the API first.
        if (
            status in {"close", "connecting"}
            and row.pairing_hint_at
            and now - row.pairing_hint_at < timedelta(minutes=2)
        ):
            status = "pairing"
            row.manual_required = True
            row.reason = "Novo pareamento indicado pela Evolution."
        if reason in {"configuration", "credentials", "not_found", "invalid_response"}:
            row.manual_required = True
        if row.manual_required or now - row.down_since >= timedelta(minutes=5):
            WhatsAppAlert.objects.get_or_create(
                state=row, incident=row.incident, recovery=False
            )
    row.status = status
    if previous != status:
        event(row, "state_changed", f"Situação: {row.get_status_display()}.")
    row.save()


def check_connection():
    reservation = claim()
    if not reservation:
        return False
    pk, token = reservation
    client = EvolutionClient()
    try:
        try:
            status, reason = client.status(), ""
        except EvolutionError as exc:
            status, reason = "error", exc.reason
        should_restart = False
        with transaction.atomic():
            row = locked(pk, token)
            if row is None:
                return False
            apply_observation(row, status, reason)
            now = timezone.now()
            manual = row.manual_requested
            # Never restart on an unreachable API, invalid session, or while the
            # Evolution itself is reconnecting. A stuck connecting state is manual.
            if (
                row.status == "connecting"
                and row.down_since
                and now - row.down_since >= timedelta(minutes=15)
            ):
                if not row.manual_required:
                    row.manual_required = True
                    event(
                        row,
                        "stalled",
                        "Reconexão sem conclusão por 15 minutos; verifique manualmente.",
                    )
            if row.status != "open" and row.attempts >= MAX_RESTART_ATTEMPTS:
                if not row.manual_required:
                    row.manual_required = True
                    event(
                        row,
                        "exhausted",
                        "Limite de três tentativas atingido; intervenção necessária.",
                    )
            if (
                row.status == "close"
                and row.attempts < MAX_RESTART_ATTEMPTS
                # The third attempt is always consumed when it is due.  A
                # stale/manual flag must not silently reduce the durable
                # three-attempt budget; after it is consumed the exhausted
                # branch below marks the incident for intervention.
                and (not row.manual_required or row.attempts == MAX_RESTART_ATTEMPTS - 1)
                and (manual or settings.EVOLUTION_AUTO_RECONNECT)
                and (
                    manual or row.next_attempt_at is None or row.next_attempt_at <= now
                )
            ):
                row.attempts += 1
                row.next_attempt_at = now + timedelta(
                    seconds=BACKOFF[min(row.attempts, 2)]
                )
                row.status = "connecting"
                event(
                    row,
                    "restart_attempt",
                    f"Tentativa {row.attempts}/{MAX_RESTART_ATTEMPTS} de reconexão da instância.",
                    row.manual_actor_id if manual else None,
                )
                should_restart = True
            row.manual_requested = False
            row.manual_actor_id = None
            if row.manual_required and row.incident:
                WhatsAppAlert.objects.get_or_create(
                    state=row, incident=row.incident, recovery=False
                )
            row.save()
        if should_restart:
            try:
                client.restart()
                description = (
                    "Comando aceito. Aguardando confirmação de conexão pela API."
                )
                reason = ""
            except EvolutionError as exc:
                description = (
                    "Não foi possível confirmar o resultado do comando de reconexão."
                )
                reason = exc.reason
            with transaction.atomic():
                row = locked(pk, token)
                if row:
                    if reason:
                        row.status = "error"
                        row.reason = REASONS.get(reason, "")
                        row.save()
                    event(row, "restart_result", description)
        return True
    finally:
        release(pk, token)


def request_action(action, actor):
    if not (actor.is_authenticated and actor.is_active and actor.is_superuser):
        raise EvolutionError("configuration")
    if not enabled() or action not in {"check", "restart", "pair"}:
        raise EvolutionError("configuration")
    row = current_state()
    with transaction.atomic():
        row = WhatsAppIntegrationState.objects.select_for_update().get(pk=row.pk)
        now = timezone.now()
        if (row.action_at and now - row.action_at < timedelta(seconds=60)) or (
            row.lease_until and row.lease_until > now
        ):
            raise EvolutionError("rate_limit")
        if action == "restart" and (row.attempts >= MAX_RESTART_ATTEMPTS or row.manual_required):
            raise EvolutionError("configuration")
        if action == "pair" and not (
            row.manual_required and row.status in {"pairing", "close", "connecting"}
        ):
            raise EvolutionError("configuration")
        row.action_at = now
        row.webhook_pending = True
        if action == "restart":
            row.manual_requested = True
            row.manual_actor_id = actor.pk
        row.save()
        event(
            row,
            "manual_action",
            {
                "check": "Verificação solicitada.",
                "restart": "Reconexão solicitada.",
                "pair": "Exibição de QR Code solicitada.",
            }[action],
            actor.pk,
        )
    return row


def receive_hint(pairing=False):
    row = current_state()
    with transaction.atomic():
        row = WhatsAppIntegrationState.objects.select_for_update().get(pk=row.pk)
        now = timezone.now()
        # Webhooks trigger polling only. Never replace a confirmed state with
        # out-of-order provider data, and never persist the raw request/QR.
        row.webhook_at = now
        row.webhook_pending = True
        if pairing:
            row.pairing_hint_at = now
        row.save(update_fields=("webhook_at", "webhook_pending", "pairing_hint_at"))
