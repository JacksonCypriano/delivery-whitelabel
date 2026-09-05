import json
import logging
import secrets
import uuid
from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from apps.tenants.admin_site import tenant_admin_site, super_admin_site
from .models import (
    BillingEvent,
    BillingCustomer,
    BillingSettings,
    Invoice,
    Plan,
    AdditionalService,
    Subscription,
)
from .forms import PurchaseForm, ManualCreditForm
from .provider import BillingError, configured, environment
from .services import (
    get_subscription,
    price_for,
    reserve_invoice,
    issue_invoice,
    reconcile_invoice,
    manual_credit,
    reserve_additional_service_invoice,
)

log = logging.getLogger("vemdedelivery.billing")


def context(request, title):
    return {**tenant_admin_site.each_context(request), "title": title}


@require_GET
def dashboard(request):
    sub = get_subscription(request.tenant)
    policy = BillingSettings.current()
    plans = []
    for plan in Plan.objects.filter(active=True):
        options = []
        for method, label in Invoice.METHODS:
            try:
                amount = price_for(plan, method, policy)
            except BillingError:
                continue
            quote = signing.dumps(
                {
                    "tenant": request.tenant.pk,
                    "plan": plan.pk,
                    "method": method,
                    "amount": str(amount),
                    "token": str(uuid.uuid4()),
                },
                salt="billing-quote",
            )
            options.append({"label": label, "amount": amount, "quote": quote})
        plans.append({"plan": plan, "options": options})
    services = []
    if sub.situation == "Em dia":
        for service in AdditionalService.objects.filter(active=True):
            options = []
            for method, label in Invoice.METHODS:
                try:
                    amount = price_for(service, method, policy)
                except BillingError:
                    continue
                options.append({"label": label, "amount": amount, "quote": signing.dumps({"tenant": request.tenant.pk, "service": service.pk, "method": method, "amount": str(amount), "token": str(uuid.uuid4())}, salt="billing-quote")})
            services.append({"service": service, "options": options})
    customer = BillingCustomer.objects.filter(
        tenant=request.tenant, environment=environment()
    ).first()
    ctx = context(request, "Minha assinatura")
    from django.core.paginator import Paginator
    history = Paginator(Invoice.objects.filter(tenant=request.tenant).select_related('fiscal_note').defer('fiscal_note__pdf_content', 'fiscal_note__xml_content'), 30).get_page(request.GET.get('pagina'))
    ctx.update(
        subscription=sub,
        plans=plans,
        services=services,
        invoices=history,
        history_page=history,
        ready=configured(),
        sandbox=environment() == "sandbox",
        customer=customer,
    )
    return render(request, "billing/dashboard.html", ctx)


@require_POST
def purchase(request):
    form = PurchaseForm(request.POST)
    try:
        if not form.is_valid():
            raise BillingError(
                "Confira nome, CPF/CNPJ e e-mail antes de gerar a cobrança."
            )
        try:
            quote = signing.loads(
                form.cleaned_data["quote"], salt="billing-quote", max_age=900
            )
        except signing.BadSignature:
            raise BillingError(
                "Oferta expirada. Atualize os planos e confirme novamente."
            )
        if quote["tenant"] != request.tenant.pk:
            raise BillingError("Oferta não pertence a esta loja.")
        from decimal import Decimal
        if "service" in quote:
            service = get_object_or_404(AdditionalService, pk=quote["service"])
            bill = reserve_additional_service_invoice(request.tenant, service, quote["method"], Decimal(quote["amount"]), uuid.UUID(quote["token"]), form.cleaned_data["name"], form.cleaned_data["document"], form.cleaned_data["email"])
        else:
            plan = get_object_or_404(Plan, pk=quote["plan"])
            bill = reserve_invoice(request.tenant, plan, quote["method"], Decimal(quote["amount"]), uuid.UUID(quote["token"]), form.cleaned_data["name"], form.cleaned_data["document"], form.cleaned_data["email"])
        try:
            issue_invoice(bill.pk)
        except BillingError as exc:
            messages.warning(request, str(exc))
        return redirect("tenant_admin:billing_invoice", invoice_id=bill.pk)
    except BillingError as exc:
        messages.error(request, str(exc))
        return redirect("tenant_admin:billing_dashboard")


@require_GET
def invoice_detail(request, invoice_id):
    bill = get_object_or_404(Invoice, pk=invoice_id, tenant=request.tenant)
    ctx = context(request, "Pagamento da assinatura")
    ctx["invoice"] = bill
    return render(request, "billing/invoice.html", ctx)


@require_POST
def refresh(request, invoice_id):
    bill = get_object_or_404(Invoice, pk=invoice_id, tenant=request.tenant)
    try:
        bill = reconcile_invoice(bill.pk)
        messages.success(
            request,
            (
                "Pagamento confirmado e meses acrescentados."
                if bill.status == "PAID"
                else "Consulta concluída: " + bill.get_status_display() + "."
            ),
        )
    except BillingError as exc:
        messages.warning(request, str(exc))
    return redirect("tenant_admin:billing_invoice", invoice_id=bill.pk)


@require_GET
def fiscal_download(request, invoice_id, kind):
    from .models import FiscalInvoice
    from .fiscal_documents import attachment_response
    from django.http import Http404
    if kind not in ('pdf', 'xml'):
        raise Http404
    note = get_object_or_404(FiscalInvoice, invoice_id=invoice_id, invoice__tenant=request.tenant)
    return attachment_response(getattr(note, kind+'_content'), getattr(note, kind+'_sha256'), f'nfse-{note.pk}.{kind}', 'application/pdf' if kind == 'pdf' else 'application/xml')


@csrf_exempt
@require_POST
def webhook(request):
    expected = settings.ASAAS_WEBHOOK_TOKEN
    if not expected or not secrets.compare_digest(
        request.headers.get("asaas-access-token", ""), expected
    ):
        return HttpResponse(status=403)
    if len(request.body) > 262144:
        return HttpResponse(status=413)
    try:
        data = json.loads(request.body)
        event_id = data["id"]
        kind = data["event"]
        if isinstance(kind, str) and kind.startswith('ACCOUNT_STATUS_'):
            account = data['account']
            payment = {"id": account["id"]}
        elif isinstance(kind, str) and kind.startswith('INVOICE_'):
            payment = data['invoice']
        elif isinstance(kind, str) and kind.startswith('CHECKOUT_'):
            payment = data.get('checkout') or data.get('payment')
        else:
            payment = data['payment']
        pid = payment["id"]
        if not all(
            isinstance(v, str) and 0 < len(v) <= 80 for v in [event_id, kind, pid]
        ):
            raise ValueError()
        from .provider import valid_id

        valid_id(pid)
    except (ValueError, KeyError, TypeError, BillingError):
        return HttpResponse(status=400)
    if not kind.startswith(("PAYMENT_", "INVOICE_", "CHECKOUT_", "ACCOUNT_STATUS_")):
        return JsonResponse({"received": True})
    with transaction.atomic():
        event, created = BillingEvent.objects.get_or_create(
            event_id=environment() + ":" + event_id,
            defaults={"payment_id": pid, "kind": kind, "environment": environment()},
        )
        if event.payment_id != pid or event.kind != kind:
            return HttpResponse(status=400)
        if not event.processed_at:

            def enqueue():
                from .tasks import process_event

                try:
                    process_event.delay(event.pk)
                except Exception:
                    log.warning(
                        "Evento salvo; envio ao worker pendente. event_pk=%s", event.pk
                    )

            transaction.on_commit(enqueue)
    return JsonResponse({"received": True})


@require_http_methods(["GET", "POST"])
def grant_manual(request, tenant_id):
    from apps.tenants.models import Tenant

    tenant = get_object_or_404(Tenant, pk=tenant_id)
    form = ManualCreditForm(
        request.POST or None, initial={"tenant_id": tenant.pk, "token": uuid.uuid4()}
    )
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["tenant_id"] != tenant.pk:
            return HttpResponse(status=400)
        manual_credit(
            tenant,
            form.cleaned_data["months"],
            form.cleaned_data["reason"],
            request.user,
            form.cleaned_data["token"],
        )
        messages.success(request, "Meses registrados com sucesso.")
        return redirect("super_admin:billing_subscription_changelist")
    return render(
        request,
        "billing/manual.html",
        {
            **super_admin_site.each_context(request),
            "title": "Registrar meses — " + tenant.name,
            "form": form,
        },
    )
