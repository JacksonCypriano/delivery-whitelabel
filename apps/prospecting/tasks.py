from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .evolution import (
    EvolutionDeliveryUnknownError,
    EvolutionInstanceUnavailableError,
    EvolutionNumberNotOnWhatsAppError,
    EvolutionReachoutRestrictedError,
    EvolutionRejectedError,
    ensure_prospecting_instance_open,
    send_prospecting_text,
)
from .message import build_prospecting_message
from .models import ProspectingControl, ProspectingQueueItem, ProspectingSentPhone


PROSPECTING_QUEUE = "prospecting"
MAX_CANDIDATES_PER_RUN = 50


def _pause_prospecting() -> None:
    ProspectingControl.objects.filter(singleton_id=1).update(enabled=False)


def _recover_stale_processing() -> int:
    cutoff = timezone.now() - timedelta(minutes=2)
    return ProspectingQueueItem.objects.filter(
        status=ProspectingQueueItem.Status.PROCESSING,
        processed_at__lt=cutoff,
    ).update(status=ProspectingQueueItem.Status.UNKNOWN)


def _claim_next_item():
    """Reserva um contato da planilha ativa mais antiga sem segurar a chamada externa."""
    with transaction.atomic():
        item = (
            ProspectingQueueItem.objects.select_for_update(skip_locked=True)
            .filter(
                status=ProspectingQueueItem.Status.PENDING,
                batch__is_active=True,
            )
            .order_by("batch__created_at", "batch_id", "created_at", "id")
            .first()
        )
        if item is None:
            return None, "empty"

        # O telefone pode estar em mais de uma planilha. Se outra planilha já
        # realizou a abordagem, basta retirar esta cópia da fila. O vínculo com
        # a planilha continua preservado em ProspectingBatchContact e o board
        # passa a contabilizá-lo como contatado pela trava global.
        if ProspectingSentPhone.objects.filter(phone=item.phone).exists():
            item.delete()
            return None, "already-contacted"

        # Reserva antes da chamada externa. Se o processo cair depois daqui,
        # a trava impede uma segunda abordagem e a recuperação marca UNKNOWN.
        try:
            ProspectingSentPhone.objects.create(phone=item.phone)
        except IntegrityError:
            item.delete()
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
    """Libera rejeição comprovada para tentativa futura sem bloquear o lead."""
    ProspectingSentPhone.objects.filter(phone=phone).delete()
    ProspectingQueueItem.objects.filter(pk=item_id).update(
        status=ProspectingQueueItem.Status.PENDING,
        processed_at=None,
    )


def _discard_cancelled_item(item_id: int, phone: str) -> None:
    """Libera uma reserva que ainda não saiu para a Evolution após remoção da planilha."""
    ProspectingSentPhone.objects.filter(phone=phone).delete()
    ProspectingQueueItem.objects.filter(pk=item_id).delete()


def _remove_confirmed_duplicates(item_id: int, phone: str) -> None:
    """Limpa cópias pendentes do telefone em outras planilhas após envio confirmado."""
    ProspectingQueueItem.objects.filter(
        phone=phone,
        status=ProspectingQueueItem.Status.PENDING,
        batch__is_active=True,
    ).exclude(pk=item_id).delete()


def _send_one():
    item_id, terminal_status = _claim_next_item()
    if item_id is None:
        return terminal_status

    item = ProspectingQueueItem.objects.select_related("batch").get(pk=item_id)

    # A planilha pode ter sido removida logo depois do claim. A checagem fica
    # imediatamente antes da chamada externa para evitar continuar a fila que
    # o superadmin acabou de excluir.
    if not item.batch.is_active:
        _discard_cancelled_item(item_id, item.phone)
        return "batch-removed"

    message = build_prospecting_message(item.establishment)

    try:
        send_prospecting_text(item.phone, message)
    except EvolutionNumberNotOnWhatsAppError:
        # Número confirmado pela própria Evolution como inexistente no
        # WhatsApp: descarta e procura outro na mesma execução sem usar cota.
        _discard_number_without_whatsapp(item_id, item.phone)
        return "not-whatsapp"
    except EvolutionReachoutRestrictedError:
        # Código 463: o WhatsApp recusou uma nova conversa. O lead não foi
        # abordado, então volta para PENDING e a automação é pausada para não
        # produzir uma sequência de falsos SENT.
        _release_rejected_item(item_id, item.phone)
        _pause_prospecting()
        return "reachout-restricted"
    except EvolutionRejectedError:
        # Rejeição operacional explícita: não perde o lead e pausa até revisão.
        _release_rejected_item(item_id, item.phone)
        _pause_prospecting()
        return "rejected"
    except EvolutionDeliveryUnknownError:
        # O request pode ter chegado ao WhatsApp, mas faltou ACK confiável.
        # Mantém a trava contra duplicidade e pausa a prospecção por segurança.
        ProspectingQueueItem.objects.filter(pk=item_id).update(
            status=ProspectingQueueItem.Status.UNKNOWN,
            processed_at=timezone.now(),
        )
        _pause_prospecting()
        return "unknown-delivery"

    ProspectingQueueItem.objects.filter(pk=item_id).update(
        status=ProspectingQueueItem.Status.SENT,
        processed_at=timezone.now(),
    )
    _remove_confirmed_duplicates(item_id, item.phone)
    return "sent"


@shared_task(
    name="apps.prospecting.tasks.send_next_prospecting_message",
    queue=PROSPECTING_QUEUE,
    soft_time_limit=50,
    time_limit=55,
)
def send_next_prospecting_message():
    """Envia até a quantidade configurada de abordagens confirmadas por minuto."""
    control = ProspectingControl.current()
    if not control.enabled:
        return "paused"
    if not control.is_allowed_at():
        return "outside-window"

    # Nenhum lead é reservado enquanto a instância estiver fora do ar. Se a
    # sessão caiu, o próprio dispatcher tenta restart e aguarda reconexão.
    try:
        connection = ensure_prospecting_instance_open()
    except EvolutionInstanceUnavailableError:
        return "instance-unavailable"

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

        if status == "sent":
            quota_used += 1
            continue

        if status in {
            "unknown-delivery",
            "reachout-restricted",
            "rejected",
        }:
            # Esses estados pausam o controle. Nunca avance para outro lead na
            # mesma rodada quando a entrega não é segura.
            break

        # not-whatsapp, already-contacted e batch-removed não consomem a cota;
        # procura o próximo candidato ainda nesta execução.

    if not statuses:
        return connection if connection == "reconnected" else "empty"
    if len(statuses) == 1:
        return statuses[0]

    sent_count = statuses.count("sent")
    unknown_count = statuses.count("unknown-delivery")
    not_whatsapp_count = statuses.count("not-whatsapp")
    return (
        f"attempted={len(statuses)};sent={sent_count};unknown={unknown_count};"
        f"not_whatsapp={not_whatsapp_count};statuses={','.join(statuses)}"
    )
