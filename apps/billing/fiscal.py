"""Emissão separada do crédito: uma falha fiscal nunca desfaz o pagamento."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from django.db import transaction
from django.utils import timezone
from .models import FiscalInvoice, FiscalSettings, TaxRate, Invoice, FiscalCustomerRule
from .provider import Asaas, BillingError, configured, environment, valid_id
from .fiscal_models import fiscal_today


def document_url(value):
    # Links devolvidos pela API autenticada; nunca baixados pelo servidor.
    if not isinstance(value, str) or len(value) > 2000:
        return ""
    try:
        url = urlsplit(value)
        return (
            value
            if url.scheme == "https"
            and url.hostname
            and not url.username
            and not url.password
            and url.port in (None, 443)
            and not any(c.isspace() for c in value)
            else ""
        )
    except ValueError:
        return ""


def payment_day(payment):
    key = (
        "confirmedDate"
        if payment.get("billingType") == "CREDIT_CARD"
        else "paymentDate"
    )
    value = payment.get(key)
    try:
        result = date.fromisoformat(value)
        if result > fiscal_today():
            raise ValueError()
        return result
    except (TypeError, ValueError):
        raise BillingError(
            "Data de confirmação ausente ou inválida no Asaas. Revisar sem substituir pela data de hoje."
        ) from None


def validate_note(note, data):
    if not isinstance(data, dict):
        raise BillingError("Resposta fiscal inválida; conciliação pendente.")
    try:
        valid = (
            data.get("payment") == note.invoice.provider_id
            and data.get("customer") == note.invoice.customer_id_external
            and Decimal(str(data.get("value"))) == note.amount
            and data.get("externalReference") == note.reference
            and data.get("effectiveDate") == str(note.effective_date)
        )
    except (InvalidOperation, TypeError):
        valid = False
    if not valid:
        raise BillingError(
            "NFS-e divergente da cobrança ou da referência fiscal. Revisão necessária."
        )
    identifier = valid_id(data.get("id"))
    if note.provider_id and identifier != note.provider_id:
        raise BillingError("Identificador fiscal divergente.")
    if data.get("status") not in dict(FiscalInvoice.STATES):
        raise BillingError("Situação fiscal não reconhecida; revisar no Asaas.")
    note.provider_id = identifier
    note.status = data["status"]
    note.number = str(data.get("number") or "")[:80]
    note.pdf_url = document_url(data.get("pdfUrl"))
    note.xml_url = document_url(data.get("xmlUrl"))
    note.notice = (
        "Revise a nota no Asaas; não gere outra sem conferir a anterior."
        if note.status == "ERROR"
        else ""
    )
    if note.review_required:
        note.notice = "Revisão fiscal pendente. Consulte a contabilidade antes de cancelar ou substituir a nota."
    if note.status in ("CANCELED", "PROCESSING_CANCELLATION", "CANCELLATION_DENIED"):
        note.review_required = True
    note.save()
    if note.status == 'AUTHORIZED':
        def enqueue_documents():
            from .tasks import archive_and_send_nfse
            try:
                archive_and_send_nfse.delay(note.pk)
            except Exception:
                pass  # A fila periódica recupera o envio ao worker.
        transaction.on_commit(enqueue_documents)


def process_fiscal(invoice_id):
    if not configured():
        return
    config = FiscalSettings.objects.filter(
        environment=environment(), enabled=True
    ).first()
    if not config or not config.start_at:
        return
    bill = Invoice.objects.get(pk=invoice_id)
    if bill.environment != environment():
        return
    existing = FiscalInvoice.objects.filter(invoice=bill).exists()
    if not existing and (
        bill.status != "PAID" or not bill.paid_at or bill.paid_at < config.start_at
    ):
        return
    note, _ = FiscalInvoice.objects.get_or_create(
        invoice=bill, defaults={"amount": bill.amount}
    )
    api = Asaas()
    try:
        # Bloqueio serializa consultas/validação. O POST ocorre apenas após gravar
        # a intenção em transação independente; timeout nunca autoriza outro POST.
        with transaction.atomic():
            note = FiscalInvoice.objects.select_for_update().get(pk=note.pk)
            bill = Invoice.objects.get(pk=note.invoice_id)
            note.last_checked_at = timezone.now()
            note.save(update_fields=["last_checked_at"])
            if bill.status == "REVIEW":
                note.review_required = True
                note.notice = "Estorno/contestação: tratar a NFS-e com a contabilidade. Cancelamento não automático."
                note.save()
            if note.provider_id:
                data = api.request("GET", "/invoices/" + valid_id(note.provider_id))
                validate_note(note, data)
                return True
            if note.attempted:
                data = api.request(
                    "GET",
                    "/invoices",
                    params={"payment": bill.provider_id, "limit": 100},
                )
                rows = data.get("data")
                if not isinstance(rows, list) or data.get("hasMore") or len(rows) != 1:
                    raise BillingError(
                        "Solicitação fiscal incerta. Confira no Asaas; o sistema não repetirá a criação."
                    )
                validate_note(note, rows[0])
                return True
            if note.review_required or bill.status != "PAID":
                return
            rule = FiscalCustomerRule.objects.filter(
                customer__tenant_id=bill.tenant_id,
                customer__environment=bill.environment,
            ).first()
            if rule and rule.hold:
                raise BillingError(
                    "Emissão pausada pela exceção fiscal deste pagador; revisar no superadmin."
                )
            payment = api.get_payment(bill.provider_id)
            # Consulta canônica sem alterar os créditos nem inverter a ordem de
            # bloqueios da rotina de pagamento (assinatura → cobrança).
            expected_state = payment.get("status") == "RECEIVED" or (
                bill.method == "CREDIT_CARD" and payment.get("status") == "CONFIRMED"
            )
            if not expected_state or payment.get("refunds") or payment.get("deleted"):
                note.review_required = True
                note.notice = "Pagamento exige revisão antes de emitir NFS-e."
                note.save()
                return
            try:
                matches = (
                    payment.get("id") == bill.provider_id
                    and payment.get("externalReference") == bill.reference
                    and payment.get("customer") == bill.customer_id_external
                    and payment.get("billingType") == bill.method
                    and Decimal(str(payment.get("value"))) == bill.amount
                )
            except InvalidOperation:
                matches = False
            if not matches:
                raise BillingError(
                    "Pagamento divergente; emissão fiscal bloqueada para revisão."
                )
            day = payment_day(payment)
            if day < timezone.localdate(
                config.start_at, timezone=ZoneInfo("America/Sao_Paulo")
            ):
                raise BillingError(
                    "Pagamento anterior ao início fiscal; revisar emissão histórica manualmente."
                )
            rate = TaxRate.objects.filter(
                configuration=config, month=day.replace(day=1), checked_at__isnull=False
            ).first()
            if not rate:
                raise BillingError(
                    "Confira a alíquota de ISS desta competência na Contabilizei e cadastre a conferência mensal no superadmin."
                )
            if bool(config.service_id) == bool(config.service_code):
                raise BillingError(
                    "Configure exatamente um ID ou código de serviço municipal no superadmin."
                )
            # Não criar outra nota se já houver uma emitida manualmente/pelo painel.
            found = api.request(
                "GET", "/invoices", params={"payment": bill.provider_id, "limit": 100}
            )
            if (
                not isinstance(found.get("data"), list)
                or found.get("data")
                or found.get("hasMore")
            ):
                raise BillingError(
                    "Já existe nota ou listagem fiscal inconclusiva para esta cobrança; revisar no Asaas."
                )
            note.effective_date = day
            note.iss = rate.iss
            note.payload = {
                "payment": bill.provider_id,
                "externalReference": note.reference,
                "serviceDescription": f"{config.description}. Plano {bill.plan_name}, {bill.months} meses.",
                "observations": f"Compra de período de assinatura. Referência: {bill.pk}.",
                "value": float(note.amount),
                "deductions": 0,
                "effectiveDate": str(day),
                "municipalServiceName": config.service_name,
                "updatePayment": False,
                "taxes": {
                    "retainIss": bool(rule and rule.retain_iss),
                    "iss": float(rate.iss),
                    "cofins": 0,
                    "csll": 0,
                    "inss": 0,
                    "ir": 0,
                    "pis": 0,
                },
                (
                    "municipalServiceId"
                    if config.service_id
                    else "municipalServiceCode"
                ): config.service_id
                or config.service_code,
            }
            note.attempted = True
            note.status = "UNCERTAIN"
            note.notice = "Solicitação iniciada; em caso de falha será apenas consultada, sem criar duplicata."
            note.save()
        data = api.request("POST", "/invoices", json=note.payload)
        with transaction.atomic():
            note = FiscalInvoice.objects.select_for_update().get(pk=note.pk)
            validate_note(note, data)
        return True
    except BillingError as exc:
        FiscalInvoice.objects.filter(pk=note.pk).update(
            notice=str(exc)[:400], last_checked_at=timezone.now()
        )


def monthly_warning(config):
    month = fiscal_today().replace(day=1)
    checked = TaxRate.objects.filter(
        configuration=config, month=month, checked_at__isnull=False
    ).first()
    if not checked:
        return "ATENÇÃO: a alíquota de ISS deste mês ainda não foi conferida. Consulte Contabilizei → Minhas Rotinas → Ver minhas alíquotas. Cadastre a competência antes de emitir. Pagamentos e acesso à loja continuam funcionando."
    return f"ISS de {month:%m/%Y}: {checked.iss}%. Última conferência: {timezone.localtime(checked.checked_at):%d/%m/%Y %H:%M}. Confira novamente no início do próximo mês e sempre que a contabilidade informar mudança."
