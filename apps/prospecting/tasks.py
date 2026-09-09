from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .evolution import (
    EvolutionDeliveryUnknownError,
    EvolutionNumberNotOnWhatsAppError,
    EvolutionRejectedError,
    send_prospecting_text,
)
from .message import build_prospecting_message
from .models import ProspectingControl, ProspectingQueueItem, ProspectingSentPhone


PROSPECTING_QUEUE = "prospecting"
MAX_CANDIDATES_PER_RUN = 50


def _recover_stale_processing() -> int:
    cutoff = timezone.now() - timedelta(minutes=2)
    return ProspectingQueueItem.objects.filter(
        status=ProspectingQueueItem.Status.PROCESSING,
        processed_at__lt=cutoff,
    ).update(status=ProspectingQueueItem.Status.UNKNOWN)


def _claim_next_item():
    """Reserva um contato sem segurar transação durante a chamada externa."""
    with transaction.atomic():
        item = (
            ProspectingQueueItem.objects.select_for_update(skip_locked=True)
            .filter(status=ProspectingQueueItem.Status.PENDING)
            .order_by("created_at", "id")
            .first()
        )
        if item is None:
            return None, "empty"

        if ProspectingSentPhone.objects.filter(phone=item.phone).exists():
            item.status = ProspectingQueueItem.Status.UNKNOWN
            item.processed_at = timezone.now()
            item.save(update_fields=["status", "processed_at"])
            return None, "already-contacted"

        # Reserva antes da chamada externa. Se o processo cair depois daqui,
        # a trava impede uma segunda abordagem e a recuperação marca UNKNOWN.
        try:
            ProspectingSentPhone.objects.create(phone=item.phone)
        except IntegrityError:
            item.status = ProspectingQueueItem.Status.UNKNOWN
            item.processed_at = timezone.now()
            item.save(update_fields=["status", "processed_at"])
            return None, "already-contacted"

        item.status = ProspectingQueueItem.Status.PROCESSING
        item.processed_at = timezone.now()
        item.save(update_fields=["status", "processed_at"])
        return item.pk, None


def _discard_number_without_whatsapp(item_id: int, phone: str) -> None:
    ProspectingSentPhone.objects.filter(phone=phone).delete()
    with transaction.atomic():
        locked = (
            ProspectingQueueItem.objects.select_for_update()
            .select_related("batch")
            .get(pk=item_id)
        )
        type(locked.batch).objects.filter(pk=locked.batch_id).update(
            failed_contacts=F("failed_contacts") + 1
        )
        locked.delete()


def _release_rejected_item(item_id: int, phone: str) -> None:
    """Libera uma rejeição operacional para nova tentativa futura, sem perder o lead."""
    ProspectingSentPhone.objects.filter(phone=phone).delete()
    ProspectingQueueItem.objects.filter(pk=item_id).update(
        status=ProspectingQueueItem.Status.PENDING,
        processed_at=None,
    )


def _send_one():
    item_id, terminal_status = _claim_next_item()
    if item_id is None:
        return terminal_status

    item = ProspectingQueueItem.objects.get(pk=item_id)
    message = build_prospecting_message(item.establishment)

    try:
        send_prospecting_text(item.phone, message)
    except EvolutionNumberNotOnWhatsAppError:
        # Número confirmado pela própria Evolution como inexistente no
        # WhatsApp: descarta e deixa o dispatcher procurar outro contato na
        # mesma execução, sem consumir a cota de mensagens enviadas.
        _discard_number_without_whatsapp(item_id, item.phone)
        return "not-whatsapp"
    except EvolutionRejectedError:
        # Rejeição explícita diferente de exists=false pode indicar problema
        # operacional/configuração. Não perde o lead: remove a trava, devolve
        # o item para PENDING e interrompe a rodada para não consumir a base.
        _release_rejected_item(item_id, item.phone)
        return "rejected"
    except EvolutionDeliveryUnknownError:
        # Timeout/rede é ambíguo: preserva a trava para nunca duplicar e conta
        # como uma vaga do minuto, pois a mensagem pode ter sido aceita.
        ProspectingQueueItem.objects.filter(pk=item_id).update(
            status=ProspectingQueueItem.Status.UNKNOWN,
            processed_at=timezone.now(),
        )
        return "unknown-delivery"

    ProspectingQueueItem.objects.filter(pk=item_id).update(
        status=ProspectingQueueItem.Status.SENT,
        processed_at=timezone.now(),
    )
    return "sent"


@shared_task(
    name="apps.prospecting.tasks.send_next_prospecting_message",
    queue=PROSPECTING_QUEUE,
    soft_time_limit=50,
    time_limit=55,
)
def send_next_prospecting_message():
    """Envia até a quantidade configurada de abordagens reais por minuto."""
    control = ProspectingControl.current()
    if not control.enabled:
        return "paused"
    if not control.is_allowed_at():
        return "outside-window"

    _recover_stale_processing()

    target = max(1, min(int(control.messages_per_minute or 1), 10))
    statuses = []
    quota_used = 0
    candidates = 0

    while quota_used < target and candidates < MAX_CANDIDATES_PER_RUN:
        status = _send_one()

        if status == "empty":
            break

        statuses.append(status)
        candidates += 1

        if status in {"sent", "unknown-delivery"}:
            quota_used += 1
            continue

        if status == "rejected":
            # Não trate uma rejeição operacional genérica como simples número
            # sem WhatsApp. Interrompe a rodada e tenta novamente só no próximo
            # disparo do Beat.
            break

        # not-whatsapp e already-contacted não consomem a cota; procura o
        # próximo candidato ainda nesta execução.

    if len(statuses) == 1:
        return statuses[0]

    sent_count = statuses.count("sent")
    unknown_count = statuses.count("unknown-delivery")
    not_whatsapp_count = statuses.count("not-whatsapp")
    return (
        f"attempted={len(statuses)};sent={sent_count};unknown={unknown_count};"
        f"not_whatsapp={not_whatsapp_count};statuses={','.join(statuses)}"
    )
