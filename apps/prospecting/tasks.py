from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .evolution import (
    EvolutionDeliveryUnknownError,
    EvolutionRejectedError,
    send_prospecting_text,
)
from .message import build_prospecting_message
from .models import ProspectingControl, ProspectingQueueItem, ProspectingSentPhone


PROSPECTING_QUEUE = "prospecting"


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


def _send_one():
    item_id, terminal_status = _claim_next_item()
    if item_id is None:
        return terminal_status

    item = ProspectingQueueItem.objects.get(pk=item_id)
    message = build_prospecting_message(item.establishment)

    try:
        send_prospecting_text(item.phone, message)
    except EvolutionRejectedError:
        # A API recusou explicitamente. Não grava o número como contatado e
        # não tenta novamente sozinha. Se o número vier em uma nova planilha,
        # poderá entrar de novo depois que a causa da rejeição for corrigida.
        ProspectingSentPhone.objects.filter(phone=item.phone).delete()
        with transaction.atomic():
            locked = ProspectingQueueItem.objects.select_for_update().select_related("batch").get(pk=item_id)
            type(locked.batch).objects.filter(pk=locked.batch_id).update(
                failed_contacts=F("failed_contacts") + 1
            )
            locked.delete()
        return "rejected"
    except EvolutionDeliveryUnknownError:
        # Timeout/rede é ambíguo: preserva a trava para nunca duplicar.
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
    """Dispatcher de prospecção, executado somente na fila dedicada."""
    control = ProspectingControl.current()
    if not control.enabled:
        return "paused"
    if not control.is_allowed_at():
        return "outside-window"

    _recover_stale_processing()

    limit = max(1, min(int(control.messages_per_minute or 1), 10))
    statuses = []

    for _ in range(limit):
        status = _send_one()
        statuses.append(status)
        if status == "empty":
            break

    if len(statuses) == 1:
        return statuses[0]

    sent_count = statuses.count("sent")
    return f"processed={len(statuses)};sent={sent_count};statuses={','.join(statuses)}"
