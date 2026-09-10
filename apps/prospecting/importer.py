from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from .models import (
    ProspectingBatch,
    ProspectingBatchContact,
    ProspectingQueueItem,
    ProspectingSentPhone,
)
from .phones import normalize_br_phone
from .xlsx_reader import read_prospecting_rows


CHUNK_SIZE = 1000


@dataclass(frozen=True)
class ProspectingImportResult:
    batch: ProspectingBatch

    @property
    def queued(self) -> int:
        return self.batch.queued_contacts


def _existing_phones(model, phones: list[str]) -> set[str]:
    found: set[str] = set()
    for start in range(0, len(phones), CHUNK_SIZE):
        chunk = phones[start : start + CHUNK_SIZE]
        found.update(model.objects.filter(phone__in=chunk).values_list("phone", flat=True))
    return found


def import_prospecting_xlsx(file_obj, *, filename: str | None = None) -> ProspectingImportResult:
    raw_rows = read_prospecting_rows(file_obj)
    total_contacts = len(raw_rows)

    candidates: dict[str, str] = {}
    invalid_contacts = 0
    duplicate_in_file = 0

    for establishment, raw_phone in raw_rows:
        establishment = " ".join((establishment or "").split()).strip()
        phone = normalize_br_phone(raw_phone)
        if not establishment or not phone:
            invalid_contacts += 1
            continue
        if phone in candidates:
            duplicate_in_file += 1
            continue
        candidates[phone] = establishment[:255]

    phones = list(candidates)
    already_sent = _existing_phones(ProspectingSentPhone, phones) if phones else set()

    # Cada planilha passa a manter o seu próprio índice e a sua própria fila.
    # Um mesmo telefone pode existir em planilhas diferentes; a trava global
    # ProspectingSentPhone continua sendo a autoridade que impede reenvio.
    pending_phones = [phone for phone in phones if phone not in already_sent]

    safe_filename = filename or getattr(file_obj, "name", "planilha.xlsx") or "planilha.xlsx"
    safe_filename = safe_filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:255]

    with transaction.atomic():
        batch = ProspectingBatch.objects.create(
            filename=safe_filename,
            total_contacts=total_contacts,
            queued_contacts=len(pending_phones),
            skipped_contacted=len(already_sent),
            skipped_duplicate=duplicate_in_file,
            invalid_contacts=invalid_contacts,
            contacts_index_complete=True,
        )

        ProspectingBatchContact.objects.bulk_create(
            [
                ProspectingBatchContact(
                    batch=batch,
                    phone=phone,
                    establishment=candidates[phone],
                )
                for phone in phones
            ],
            batch_size=CHUNK_SIZE,
        )

        ProspectingQueueItem.objects.bulk_create(
            [
                ProspectingQueueItem(
                    batch=batch,
                    phone=phone,
                    establishment=candidates[phone],
                )
                for phone in pending_phones
            ],
            batch_size=CHUNK_SIZE,
        )

    return ProspectingImportResult(batch=batch)
