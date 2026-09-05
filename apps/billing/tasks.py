import logging
import uuid
import time
from datetime import timedelta
from celery import shared_task
from django.db.models import F, Q
from django.utils import timezone
from .models import BillingEvent, Invoice, OrderPayment
from .provider import Asaas, BillingError, environment, configured
from .services import reconcile_invoice, apply_payment, suspend_due

log = logging.getLogger("vemdedelivery.billing")


@shared_task
def archive_and_send_nfse(note_id):
    from .fiscal_documents import deliver_documents
    deliver_documents(note_id)


@shared_task
def retry_nfse_documents():
    from .models import FiscalInvoice
    if not configured():
        return
    stale = timezone.now() - timedelta(minutes=5)
    rows = FiscalInvoice.objects.filter(status='AUTHORIZED', invoice__environment=environment()).filter(Q(delivery_checked_at__isnull=True) | Q(delivery_checked_at__lte=stale)).filter(Q(pdf_content__isnull=True) | Q(xml_content__isnull=True) & ~Q(xml_url='') | Q(delivery_status='PENDING')).order_by(F('delivery_checked_at').asc(nulls_first=True)).values_list('pk', flat=True)[:20]
    started = time.monotonic()
    for pk in rows:
        if time.monotonic() - started > 30:
            break
        archive_and_send_nfse(pk)


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
        if event.kind.startswith('CHECKOUT_'):
            from .online import apply_checkout_event
            from .provider import valid_id
            payment = OrderPayment.objects.filter(checkout_id=valid_id(event.payment_id)).first()
            if payment:
                account = getattr(payment.tenant, 'payment_account', None)
                if not account or not account.is_ready:
                    raise BillingError('Subconta do pedido não está disponível.')
                checkout = Asaas(api_key=account.get_api_key()).get_checkout(payment.checkout_id)
                apply_checkout_event(payment.checkout_id, checkout, event.kind)
            BillingEvent.objects.filter(pk=event.pk).update(processed_at=timezone.now())
            return
        if event.kind.startswith('INVOICE_'):
            from .fiscal import process_fiscal
            from .models import FiscalInvoice
            from .provider import valid_id
            data = Asaas().request('GET', '/invoices/' + event.payment_id)
            bill = Invoice.objects.filter(provider_id=valid_id(data.get('payment')), environment=environment()).first()
            if bill:
                if not process_fiscal(bill.pk):
                    return
                if not FiscalInvoice.objects.filter(invoice=bill, provider_id=event.payment_id).exists():
                    return
            BillingEvent.objects.filter(pk=event.pk).update(processed_at=timezone.now())
            return
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
    # Também consulta checkouts dos pedidos online caso o webhook tenha sido perdido.
    from .online import refresh_order_payment
    for payment in OrderPayment.objects.filter(status="PENDING").select_related("tenant")[:50]:
        try:
            refresh_order_payment(payment)
        except BillingError:
            log.warning("Pagamento de pedido aguardando conciliação. order_id=%s", payment.order_id)


@shared_task
def reconcile_fiscal_invoices():
    from .models import FiscalSettings, FiscalInvoice
    from .fiscal import process_fiscal
    if not configured():
        return
    config = FiscalSettings.objects.filter(environment=environment(), enabled=True).first()
    if not config or not config.start_at:
        return
    # Planos e serviços avulsos possuem a mesma obrigação fiscal: uma NFS-e por cobrança paga.
    for bill in Invoice.objects.filter(status='PAID', environment=environment(), paid_at__gte=config.start_at, fiscal_note__isnull=True)[:100]:
        FiscalInvoice.objects.get_or_create(invoice=bill, defaults={'amount': bill.amount})
    stale = timezone.now() - timedelta(hours=6)
    queue = FiscalInvoice.objects.filter(invoice__environment=environment()).filter(
        Q(last_checked_at__isnull=True) | Q(last_checked_at__lte=stale) |
        Q(status__in=['PENDING', 'UNCERTAIN', 'SCHEDULED', 'SYNCHRONIZED'])
    ).order_by(F('last_checked_at').asc(nulls_first=True))
    started = time.monotonic()
    for pk in queue.values_list('invoice_id', flat=True)[:50]:
        if time.monotonic() - started > 30:
            break
        try:
            process_fiscal(pk)
        except Exception:
            FiscalInvoice.objects.filter(invoice_id=pk).update(notice='Falha fiscal inesperada; revisão técnica necessária. O pagamento permanece preservado.', last_checked_at=timezone.now())
            log.error('Falha fiscal pendente de revisão. invoice_id=%s', pk)
