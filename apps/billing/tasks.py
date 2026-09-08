import logging
import uuid
import time
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from celery import shared_task
from django.db import transaction
from django.db.models import F, Q
from django.contrib.auth import get_user_model
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from .models import BillingEvent, Invoice, OrderPayment, TaxRateWhatsAppReminder
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
        if event.kind.startswith('ACCOUNT_STATUS_'):
            from .online import account_status_from_event, apply_subaccount_status

            status = account_status_from_event(event.kind)
            if status:
                reason = "O cadastro da subconta foi rejeitado; revise os dados no Asaas."
                apply_subaccount_status(event.payment_id, status, reason)
            # Unknown account-status variants are acknowledged so a newly
            # introduced Asaas event cannot block the provider queue.
            BillingEvent.objects.filter(pk=event.pk).update(processed_at=timezone.now())
            return
        if event.kind.startswith('CHECKOUT_'):
            from .online import apply_checkout_event
            from .provider import valid_id
            payment = OrderPayment.objects.filter(checkout_id=valid_id(event.payment_id)).first()
            if payment:
                account = getattr(payment.tenant, 'payment_account', None)
                if not account or not account.provider_account_id or not account.encrypted_api_key:
                    raise BillingError('Subconta do pedido não está disponível.')
                # Uma liberação pode ser retirada depois que o checkout foi
                # emitido. Pagamentos já existentes continuam conciliáveis.
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
    # Webhooks are the primary path; this bounded fallback covers a temporary
    # callback/DNS outage without making approval depend on a manual action.
    from .online import sync_pending_subaccounts
    sync_pending_subaccounts(limit=50)


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



def _tax_rate_admin_url(alert):
    current = alert["current"]
    if current:
        path = reverse("super_admin:billing_taxrate_change", args=[current.pk])
    else:
        query = {
            "configuration": alert["configuration"].pk,
            "month": alert["month"].isoformat(),
        }
        previous = alert["previous"]
        if previous:
            query["iss"] = str(previous.iss)
        path = reverse("super_admin:billing_taxrate_add") + "?" + urlencode(query)

    base = (getattr(settings, "SUPERADMIN_PUBLIC_URL", "") or "").strip().rstrip("/")
    if not base:
        base = (getattr(settings, "CUSTOMER_PORTAL_URL", "") or "").strip().rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return ""
    return base + path


def _tax_rate_whatsapp_message(alert, action_url):
    month = alert["month"]
    previous = alert["previous"]
    previous_line = ""
    if previous:
        previous_line = (
            f"\nÚltima alíquota confirmada: {previous.iss}% "
            f"({previous.month:%m/%Y})."
        )
    contabilizei_url = getattr(
        settings,
        "CONTABILIZEI_TAX_RATES_URL",
        "https://app.contabilizei.com.br/painel-de-controle/#/minhas-aliquotas",
    )
    return (
        "⚠️ VemDeDelivery — conferência mensal do ISS\n\n"
        f"A alíquota de ISS de {month:%m/%Y} ainda não foi confirmada."
        f"{previous_line}\n\n"
        "1) Confira a alíquota na Contabilizei:\n"
        f"{contabilizei_url}\n\n"
        "2) Depois confirme ou ajuste no Superadmin do VemDeDelivery:\n"
        f"{action_url}\n\n"
        "Enquanto a competência não for confirmada, a emissão automática de NFS-e fica bloqueada. "
        "Cobranças e acesso às lojas continuam funcionando."
    )


@shared_task(soft_time_limit=60, time_limit=90)
def send_tax_rate_whatsapp_reminders():
    """Envia uma confirmação mensal do ISS aos superusuários com WhatsApp.

    Roda diariamente para recuperar indisponibilidades do Celery/Evolution, mas um
    envio confirmado é persistido por usuário + competência e não é repetido.
    """
    from apps.billing.fiscal import current_tax_rate_alert
    from apps.integrations.whatsapp.client import EvolutionClient, EvolutionError
    from apps.integrations.whatsapp.service import normalize_br_phone

    alert = current_tax_rate_alert()
    if not alert:
        return 0
    action_url = _tax_rate_admin_url(alert)
    if not action_url:
        log.error("Lembrete mensal de ISS não enviado: SUPERADMIN_PUBLIC_URL inválida.")
        return 0

    User = get_user_model()
    sent = 0
    for user in (
        User.objects.filter(is_superuser=True, is_active=True)
        .exclude(administrative_whatsapp="")
        .order_by("pk")
    ):
        try:
            phone = normalize_br_phone(user.administrative_whatsapp)
        except ValueError:
            log.error("WhatsApp administrativo inválido para superusuário pk=%s.", user.pk)
            continue

        now = timezone.now()
        with transaction.atomic():
            reminder, _ = TaxRateWhatsAppReminder.objects.select_for_update().get_or_create(
                configuration=alert["configuration"],
                month=alert["month"],
                recipient=user,
                defaults={"phone": phone},
            )
            if reminder.status == "SENT":
                continue
            if (
                reminder.status == "SENDING"
                and reminder.attempted_at
                and reminder.attempted_at > now - timedelta(hours=1)
            ):
                continue
            reminder.phone = phone
            reminder.status = "SENDING"
            reminder.attempts = F("attempts") + 1
            reminder.attempted_at = now
            reminder.last_error = ""
            reminder.save(
                update_fields=[
                    "phone",
                    "status",
                    "attempts",
                    "attempted_at",
                    "last_error",
                ]
            )

        try:
            EvolutionClient().send_text(
                phone,
                _tax_rate_whatsapp_message(alert, action_url),
            )
        except EvolutionError as exc:
            TaxRateWhatsAppReminder.objects.filter(pk=reminder.pk).update(
                status="FAILED",
                last_error=str(getattr(exc, "reason", "unavailable"))[:80],
            )
            continue
        except Exception:
            log.exception("Falha inesperada ao enviar lembrete mensal de ISS.")
            TaxRateWhatsAppReminder.objects.filter(pk=reminder.pk).update(
                status="FAILED",
                last_error="unexpected",
            )
            continue

        TaxRateWhatsAppReminder.objects.filter(pk=reminder.pk).update(
            status="SENT",
            sent_at=timezone.now(),
            last_error="",
        )
        sent += 1
    return sent


def _asaas_fee_admin_url():
    path = reverse("super_admin:billing_asaasfeesnapshot_changelist")
    base = (getattr(settings, "SUPERADMIN_PUBLIC_URL", "") or "").strip().rstrip("/")
    if not base:
        base = (getattr(settings, "CUSTOMER_PORTAL_URL", "") or "").strip().rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return ""
    return base + path


def _money(value):
    return "-" if value is None else f"R$ {value:.2f}".replace(".", ",")


def _percent(value):
    return "-" if value is None else f"{value:.2f}%".replace(".", ",")


def _asaas_fee_change_message(snapshot, previous, action_url):
    fields = [
        ("Pix", "pix_fee", _money),
        ("Cartão 1x", "card_1x_percent", _percent),
        ("Fixa cartão", "card_fixed_fee", _money),
        ("NFS-e", "nfse_fee", _money),
        ("Criação de subconta", "child_account_fee", _money),
    ]
    changes = []
    for label, field, formatter in fields:
        before = getattr(previous, field, None)
        after = getattr(snapshot, field, None)
        if before != after:
            changes.append(f"• {label}: {formatter(before)} → {formatter(after)}")
    if not changes:
        changes.append("• As condições comerciais ou a data de uma promoção foram alteradas.")
    return (
        "⚠️ VemDeDelivery — taxas do Asaas alteradas\n\n"
        + "\n".join(changes)
        + "\n\nO Asaas é a fonte de verdade dessas tarifas. Revise o snapshot no Superadmin:\n"
        + action_url
    )


def _asaas_fee_expiration_message(snapshot, days, action_url):
    return (
        "⚠️ VemDeDelivery — promoção do Asaas próxima do vencimento\n\n"
        f"A próxima condição promocional registrada vence em {snapshot.discount_expires_at:%d/%m/%Y}.\n"
        f"Faltam aproximadamente {days} dia(s). Depois disso, as tarifas efetivas podem mudar.\n\n"
        "Revise as condições no Superadmin:\n"
        + action_url
    )


def _send_fee_whatsapp(text):
    from apps.integrations.whatsapp.client import EvolutionClient, EvolutionError
    from apps.integrations.whatsapp.service import normalize_br_phone

    User = get_user_model()
    sent = 0
    for user in (
        User.objects.filter(is_superuser=True, is_active=True)
        .exclude(administrative_whatsapp="")
        .order_by("pk")
    ):
        try:
            phone = normalize_br_phone(user.administrative_whatsapp)
            EvolutionClient().send_text(phone, text)
            sent += 1
        except (ValueError, EvolutionError):
            log.warning("Não foi possível enviar o alerta de taxas Asaas ao superusuário pk=%s.", user.pk)
        except Exception:
            log.exception("Falha inesperada ao enviar alerta de taxas Asaas.")
    return sent


@shared_task(soft_time_limit=60, time_limit=90)
def monitor_asaas_fees():
    """Persist changes in Asaas fees and alert only on meaningful transitions."""
    if not configured():
        return 0

    from .fees import sync_platform_fee_snapshot
    from .models import AsaasFeeSnapshot

    snapshot, changed, _summary = sync_platform_fee_snapshot()
    action_url = _asaas_fee_admin_url()
    if not action_url:
        log.error("Monitor de taxas Asaas sem URL pública válida do Superadmin.")
        return 0

    sent = 0
    state = dict(snapshot.notification_state or {})
    previous = (
        AsaasFeeSnapshot.objects.filter(
            environment=snapshot.environment,
            observed_at__lt=snapshot.observed_at,
        )
        .order_by("-observed_at")
        .first()
    )

    if changed and previous and not state.get("change"):
        if _send_fee_whatsapp(_asaas_fee_change_message(snapshot, previous, action_url)):
            state["change"] = timezone.now().isoformat()
            sent += 1

    expiration = snapshot.discount_expires_at
    if expiration and expiration > timezone.now():
        days = max(0, (timezone.localtime(expiration).date() - timezone.localdate()).days)
        threshold = 1 if days <= 1 else 7 if days <= 7 else 30 if days <= 30 else None
        if threshold is not None:
            key = f"promotion_{threshold}d"
            if not state.get(key):
                if _send_fee_whatsapp(_asaas_fee_expiration_message(snapshot, days, action_url)):
                    state[key] = timezone.now().isoformat()
                    sent += 1

    if state != (snapshot.notification_state or {}):
        AsaasFeeSnapshot.objects.filter(pk=snapshot.pk).update(notification_state=state)
    return sent
