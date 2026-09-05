import calendar
import logging
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.tenants.models import Tenant
from .models import (
    BillingSettings,
    Subscription,
    Invoice,
    BillingCustomer,
    Credit,
    BillingAudit,
    Plan,
    AdditionalService,
)
from .provider import (
    Asaas,
    BillingError,
    ProviderUnavailable,
    ProviderRejected,
    environment,
    configured,
    payment_url,
    valid_id,
)

log = logging.getLogger("vemdedelivery.billing")


def audit(sub, action, detail="", actor=None):
    BillingAudit.objects.create(
        tenant_id=sub.tenant_id, action=action, detail=detail[:500], actor=actor
    )


def get_subscription(tenant):
    return Subscription.objects.get_or_create(
        tenant=tenant, defaults={"manually_blocked": not tenant.is_active}
    )[0]


def price_for(plan, method, policy=None):
    policy = policy or BillingSettings.current()
    if method not in dict(Invoice.METHODS):
        raise BillingError("Forma de pagamento inválida.")
    if not getattr(
        policy,
        {
            "PIX": "pix_enabled",
            "BOLETO": "boleto_enabled",
            "CREDIT_CARD": "card_enabled",
        }[method],
    ):
        raise BillingError("Esta forma de pagamento não está habilitada.")
    value = plan.price
    if method == "CREDIT_CARD":
        value = max(
            value,
            (value - policy.fixed_pix_fee + policy.card_fixed_fee)
            / (1 - policy.card_percent / 100),
        )
    return value.quantize(Decimal(".01"), rounding=ROUND_CEILING)


def add_months(day, months, anchor):
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return day.replace(
        year=year, month=month, day=min(anchor, calendar.monthrange(year, month)[1])
    )


def set_store(sub):
    # Sempre chamado com lock na assinatura; todos os caminhos de escrita usam essa ordem.
    tenant = Tenant.objects.select_for_update().get(pk=sub.tenant_id)
    active = not (sub.manually_blocked or sub.payment_review or sub.billing_suspended)
    if tenant.is_active != active:
        Tenant.objects.filter(pk=tenant.pk).update(is_active=active)


def extend_locked(sub, months, invoice=None, actor=None, reason="", manual_token=None):
    today = timezone.localdate()
    previous = sub.valid_until
    if previous and previous > today:
        start = previous
    else:
        start = today
        sub.anchor_day = today.day
    end = add_months(start, months, sub.anchor_day)
    kwargs = {
        "invoice": invoice,
        "tenant_id": sub.tenant_id,
        "months": months,
        "previous_until": previous,
        "valid_until": end,
        "reason": reason,
        "actor": actor,
    }
    if manual_token:
        kwargs["manual_token"] = manual_token
    credit = Credit.objects.create(**kwargs)
    sub.valid_until = end
    sub.managed = True
    sub.billing_suspended = False
    sub.save()
    set_store(sub)
    audit(
        sub,
        "Meses creditados",
        f"{months} meses; vencimento {previous} → {end}; {reason}",
        actor,
    )
    return credit


@transaction.atomic
def manual_credit(tenant, months, reason, actor, token):
    if not actor.is_active or not actor.is_superuser:
        raise BillingError("Sem permissão.")
    if not 1 <= months <= 36 or not reason.strip():
        raise BillingError("Informe meses e justificativa.")
    get_subscription(tenant)
    sub = Subscription.objects.select_for_update().get(tenant=tenant)
    existing = Credit.objects.filter(manual_token=token).first()
    if existing:
        if existing.tenant_id != tenant.pk:
            raise BillingError("Operação inválida.")
        return existing
    return extend_locked(sub, months, actor=actor, reason=reason, manual_token=token)


def suspend_due(today=None):
    if not settings.BILLING_ENABLED:
        return 0
    today = today or timezone.localdate()
    policy = BillingSettings.current()
    count = 0
    for pk in (
        Subscription.objects.filter(managed=True, billing_suspended=False)
        .values_list("pk", flat=True)
        .iterator()
    ):
        with transaction.atomic():
            sub = Subscription.objects.select_for_update().get(pk=pk)
            grace = sub.grace_days if sub.grace_days is not None else policy.grace_days
            if not sub.managed or sub.billing_suspended:
                continue
            if (
                sub.valid_until is not None
                and sub.valid_until + timedelta(days=grace) > today
            ):
                continue
            sub.billing_suspended = True
            sub.save(update_fields=["billing_suspended"])
            set_store(sub)
            audit(
                sub,
                "Suspensão automática",
                f"Verificação diária; vencimento {sub.valid_until}; tolerância {grace} dias.",
            )
            count += 1
    return count


def reserve_invoice(tenant, plan, method, amount, token, name, document, email):
    if not configured():
        raise BillingError("Pagamentos ainda não configurados. Fale com o suporte.")
    with transaction.atomic():
        get_subscription(tenant)
        sub = Subscription.objects.select_for_update().get(tenant=tenant)
        existing = Invoice.objects.filter(pk=token).first()
        if existing:
            if existing.tenant_id != tenant.pk:
                raise BillingError("Operação inválida.")
            return existing
        plan = Plan.objects.select_for_update().get(pk=plan.pk)
        value = price_for(plan, method)
        if not plan.active or value != amount:
            raise BillingError("O preço mudou. Confira os planos e confirme novamente.")
        # Uma cobrança em andamento por loja evita duplo clique e duas abas com tokens diferentes.
        existing = Invoice.objects.filter(
            tenant=tenant,
            environment=environment(),
            status__in=["NEW", "UNCERTAIN", "PENDING"],
        ).first()
        if existing:
            return existing
        customer, _ = BillingCustomer.objects.get_or_create(
            tenant=tenant,
            environment=environment(),
            defaults={"name": name, "document": document, "email": email},
        )
        if not customer.provider_id and not customer.attempted:
            customer.name = name
            customer.document = document
            customer.email = email
            customer.save()
        if customer.document != document and customer.provider_id:
            raise BillingError(
                "O CPF/CNPJ difere do cadastro financeiro existente. Solicite a atualização ao suporte."
            )
        return Invoice.objects.create(
            id=token,
            tenant=tenant,
            plan_name=plan.name,
            months=plan.months,
            amount=value,
            method=method,
            environment=environment(),
            due_date=timezone.localdate() + timedelta(days=2),
        )


def reserve_additional_service_invoice(tenant, service, method, amount, token, name, document, email):
    """Cria cobrança de serviço avulso; não concede meses de assinatura."""
    if not configured():
        raise BillingError("Pagamentos ainda não configurados. Fale com o suporte.")
    with transaction.atomic():
        sub = Subscription.objects.select_for_update().get_or_create(tenant=tenant)[0]
        if not sub.managed or sub.billing_suspended or sub.manually_blocked or sub.payment_review:
            raise BillingError("Serviços adicionais estão disponíveis somente para lojas com assinatura ativa.")
        existing = Invoice.objects.filter(pk=token).first()
        if existing:
            if existing.tenant_id != tenant.pk:
                raise BillingError("Operação inválida.")
            return existing
        service = AdditionalService.objects.select_for_update().get(pk=service.pk, active=True)
        value = price_for(service, method)
        if value != amount:
            raise BillingError("O preço do serviço mudou. Confira e tente novamente.")
        customer, _ = BillingCustomer.objects.get_or_create(tenant=tenant, environment=environment(), defaults={"name": name, "document": document, "email": email})
        if not customer.provider_id and not customer.attempted:
            customer.name, customer.document, customer.email = name, document, email
            customer.save()
        return Invoice.objects.create(id=token, tenant=tenant, additional_service=service, plan_name=service.name, months=0, amount=value, method=method, environment=environment(), due_date=timezone.localdate() + timedelta(days=2))


def issue_invoice(invoice_id):
    api = Asaas()
    # Marcadores de tentativa são commitados ANTES da chamada externa: timeout/crash
    # nunca dispara outro POST de pagamento automaticamente.
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
        if invoice.environment != environment():
            raise BillingError("Cobrança pertence a outro ambiente.")
        if invoice.provider_id or invoice.issuance_attempted:
            return invoice
        if invoice.status in ("ERROR", "CANCELLED", "REVIEW", "PAID"):
            return invoice
        if invoice.due_date < timezone.localdate():
            invoice.status = "ERROR"
            invoice.save(update_fields=["status"])
            return invoice
        invoice.status = "UNCERTAIN"
        invoice.save()
    customer = None
    try:
        customer = BillingCustomer.objects.get(
            tenant_id=invoice.tenant_id, environment=invoice.environment
        )
        ref = f"vdd-customer:{invoice.environment}:{invoice.tenant_id}"
        if not customer.provider_id:
            data = api.find_customer(ref)
            rows = data.get("data", [])
            if len(rows) > 1 or data.get("hasMore"):
                raise BillingError(
                    "Cadastro financeiro duplicado no provedor; solicite revisão."
                )
            if rows:
                found = rows[0]
                if (
                    found.get("externalReference") != ref
                    or found.get("cpfCnpj") != customer.document
                ):
                    raise BillingError(
                        "Cadastro financeiro divergente; solicite revisão."
                    )
            else:
                with transaction.atomic():
                    locked = BillingCustomer.objects.select_for_update().get(
                        pk=customer.pk
                    )
                    if locked.attempted:
                        raise BillingError(
                            "Cadastro aguardando conciliação; solicite revisão."
                        )
                    locked.attempted = True
                    locked.save(update_fields=["attempted"])
                found = api.create_customer(
                    {
                        "name": customer.name,
                        "cpfCnpj": customer.document,
                        "email": customer.email,
                        "externalReference": ref,
                        "notificationDisabled": True,
                    }
                )
            customer.provider_id = valid_id(found.get("id"))
            customer.save(update_fields=["provider_id"])
        with transaction.atomic():
            locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
            if locked.provider_id or locked.issuance_attempted:
                return locked
            locked.customer_id_external = customer.provider_id
            locked.issuance_attempted = True
            locked.save(update_fields=["customer_id_external", "issuance_attempted"])
        body = {
            "customer": customer.provider_id,
            "billingType": invoice.method,
            "value": float(invoice.amount),
            "dueDate": str(invoice.due_date),
            "description": f"VemDeDelivery — {invoice.plan_name} ({invoice.months} meses)",
            "externalReference": invoice.reference,
            "postalService": False,
            "interest": {"value": 0},
            "fine": {"value": 0},
        }
        payment = api.create_payment(body)
        identifier = valid_id(payment.get("id"))
        # Não libera crédito por resposta de criação. Conciliação consulta o pagamento.
        Invoice.objects.filter(pk=invoice.pk, status__in=["NEW", "UNCERTAIN"]).update(
            provider_id=identifier,
            checkout_url=payment_url(payment.get("invoiceUrl", "")),
            status="PENDING",
        )
        invoice.refresh_from_db()
        return invoice
    except ProviderRejected:
        Invoice.objects.filter(pk=invoice.pk).update(status="ERROR")
        if customer is not None and not customer.provider_id:
            BillingCustomer.objects.filter(pk=customer.pk).update(attempted=False)
        raise
    except BillingError:
        log.warning("Emissão pendente de conciliação. invoice_id=%s", invoice_id)
        raise


def reconcile_invoice(invoice_id):
    invoice = Invoice.objects.get(pk=invoice_id)
    if invoice.environment != environment():
        raise BillingError("Ambiente de cobrança diferente.")
    api = Asaas()
    Invoice.objects.filter(pk=invoice.pk).update(last_checked_at=timezone.now())
    if invoice.provider_id:
        payment = api.get_payment(invoice.provider_id)
    else:
        data = api.find_payment(invoice.reference)
        rows = data.get("data", [])
        if not rows:
            if not invoice.issuance_attempted and invoice.status in (
                "NEW",
                "UNCERTAIN",
            ):
                return issue_invoice(invoice.pk)
            return invoice
        if len(rows) != 1 or data.get("hasMore"):
            raise BillingError("Mais de uma cobrança encontrada; revisão necessária.")
        payment = rows[0]
    return apply_payment(invoice.pk, payment)


@transaction.atomic
def apply_payment(invoice_id, payment):
    initial = Invoice.objects.get(pk=invoice_id)
    sub = Subscription.objects.select_for_update().get(tenant_id=initial.tenant_id)
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    if invoice.environment != environment() or (
        invoice.environment == "sandbox"
        and not getattr(settings, "BILLING_ALLOW_SANDBOX", True)
    ):
        raise BillingError("Ambiente incompatível.")
    try:
        amount = Decimal(str(payment["value"]))
    except (KeyError, ValueError, ArithmeticError):
        raise BillingError("Valor inválido no provedor.")
    identifier = valid_id(payment.get("id"))
    if (
        payment.get("externalReference") != invoice.reference
        or amount != invoice.amount
        or payment.get("billingType") != invoice.method
        or payment.get("customer") != invoice.customer_id_external
        or not invoice.customer_id_external
        or (invoice.provider_id and invoice.provider_id != identifier)
    ):
        raise BillingError("Pagamento divergente; nenhum crédito aplicado.")
    state = payment.get("status")
    invoice.provider_id = identifier
    invoice.checkout_url = (
        payment_url(payment.get("invoiceUrl", "")) or invoice.checkout_url
    )
    invoice.last_checked_at = timezone.now()
    adverse = {
        "REFUNDED",
        "REFUND_REQUESTED",
        "REFUND_IN_PROGRESS",
        "CHARGEBACK_REQUESTED",
        "CHARGEBACK_DISPUTE",
        "AWAITING_CHARGEBACK_REVERSAL",
    }
    if state in adverse or payment.get("refunds"):
        entering_review = invoice.status != "REVIEW"
        invoice.status = "REVIEW"
        if Credit.objects.filter(invoice=invoice).exists():
            sub.payment_review = True
            sub.save(update_fields=["payment_review"])
            set_store(sub)
            if entering_review:
                audit(
                    sub,
                    "Estorno ou contestação",
                    f"Cobrança {invoice.pk}; revisão administrativa necessária.",
                )
    elif state == "RECEIVED" or (
        invoice.method == "CREDIT_CARD" and state == "CONFIRMED"
    ):
        if (
            invoice.status != "REVIEW"
            and not Credit.objects.filter(invoice=invoice).exists()
        ):
            # Serviço avulso é pago e faturado, mas não renova a assinatura.
            if invoice.months:
                extend_locked(
                    sub, invoice.months, invoice=invoice, reason=f"Pagamento {invoice.pk}"
                )
            invoice.paid_at = timezone.now()
        if invoice.status != "REVIEW":
            invoice.status = "PAID"
    elif (
        not Credit.objects.filter(invoice=invoice).exists()
        and invoice.status != "REVIEW"
    ):
        invoice.status = (
            "CANCELLED"
            if payment.get("deleted")
            else ("OVERDUE" if state == "OVERDUE" else "PENDING")
        )
    invoice.save()
    return invoice
