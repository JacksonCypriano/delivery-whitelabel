import logging
import uuid
import time
from datetime import timedelta
from celery import shared_task
from django.db.models import F, Q
from django.utils import timezone
from .models import BillingEvent, Invoice
from .provider import Asaas, BillingError, environment, configured
from .services import reconcile_invoice, apply_payment, suspend_due

log = logging.getLogger("vemdedelivery.billing")


@shared_task
def suspend_expired_subscriptions():
    return suspend_due()


@shared_task
def process_event(event_pk):
    event = BillingEvent.objects.get(pk=event_pk)
    if event.processed_at or event.environment != environment() or not configured():
        return
    BillingEvent.objects.filter(pk=event.pk).update(attempts=F("attempts") + 1)
    try:
        payment = Asaas().get_payment(event.payment_id)
        reference = payment.get("externalReference") or ""
        prefix = f"vdd-billing:{environment()}:"
        if not isinstance(reference, str) or not reference.startswith(prefix):
            BillingEvent.objects.filter(pk=event.pk).update(processed_at=timezone.now())
            return
        try:
            invoice_id = uuid.UUID(reference[len(prefix) :])
        except ValueError:
            raise BillingError("Referência inválida.")
        if not Invoice.objects.filter(
            pk=invoice_id, environment=environment()
        ).exists():
            raise BillingError("Cobrança local não localizada.")
        apply_payment(invoice_id, payment)
        BillingEvent.objects.filter(pk=event.pk).update(processed_at=timezone.now())
    except BillingError:
        log.warning("Conciliação pendente. event_pk=%s", event_pk)


@shared_task
def reconcile_pending_payments():
    if not configured():
        return
    # Reprocessa eventos persistidos mesmo se o broker estava indisponível ao receber o webhook.
    started = time.monotonic()
    for pk in (
        BillingEvent.objects.filter(
            processed_at__isnull=True, environment=environment()
        )
        .order_by("attempts", "created_at")
        .values_list("pk", flat=True)[:50]
    ):
        if time.monotonic() - started > 30:
            break
        process_event(pk)
    # Rotação de cobranças ativas. Pagas também são revisitadas para recuperar
    # estornos/contestações se algum webhook tiver sido perdido.
    stale = timezone.now() - timedelta(days=1)
    query = Q(status__in=["NEW", "UNCERTAIN", "PENDING", "OVERDUE"]) | Q(
        status="PAID", last_checked_at__lte=stale
    )
    ids = list(
        Invoice.objects.filter(query, environment=environment())
        .order_by(F("last_checked_at").asc(nulls_first=True), "created_at")
        .values_list("pk", flat=True)[:50]
    )
    started = time.monotonic()
    for pk in ids:
        if time.monotonic() - started > 30:
            break
        try:
            reconcile_invoice(pk)
        except BillingError:
            log.warning("Cobrança aguardando conciliação. invoice_id=%s", pk)
