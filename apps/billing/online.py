"""Online order payments routed to the store's Asaas subaccount."""
import logging
import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import OrderPayment, TenantPaymentAccount
from .asaas_fields import (
    COMPANY_TYPES,
    clean_document as clean_asaas_document,
    document_kind,
    normalize_brazilian_phone,
)
from .provider import Asaas, BillingError, configured, environment, payment_url, valid_id


ONLINE_METHODS = {"pix": "PIX", "credit_card": "CREDIT_CARD"}

ACCOUNT_STATUS_EVENTS = (
    "ACCOUNT_STATUS_BANK_ACCOUNT_INFO_APPROVED",
    "ACCOUNT_STATUS_BANK_ACCOUNT_INFO_AWAITING_APPROVAL",
    "ACCOUNT_STATUS_BANK_ACCOUNT_INFO_PENDING",
    "ACCOUNT_STATUS_BANK_ACCOUNT_INFO_REJECTED",
    "ACCOUNT_STATUS_COMMERCIAL_INFO_APPROVED",
    "ACCOUNT_STATUS_COMMERCIAL_INFO_AWAITING_APPROVAL",
    "ACCOUNT_STATUS_COMMERCIAL_INFO_PENDING",
    "ACCOUNT_STATUS_COMMERCIAL_INFO_REJECTED",
    "ACCOUNT_STATUS_DOCUMENT_APPROVED",
    "ACCOUNT_STATUS_DOCUMENT_AWAITING_APPROVAL",
    "ACCOUNT_STATUS_DOCUMENT_PENDING",
    "ACCOUNT_STATUS_DOCUMENT_REJECTED",
    "ACCOUNT_STATUS_GENERAL_APPROVAL_APPROVED",
    "ACCOUNT_STATUS_GENERAL_APPROVAL_AWAITING_APPROVAL",
    "ACCOUNT_STATUS_GENERAL_APPROVAL_PENDING",
    "ACCOUNT_STATUS_GENERAL_APPROVAL_REJECTED",
)

log = logging.getLogger("vemdedelivery.billing")


def _clean_document(value):
    return re.sub(r"[^0-9A-Za-z]", "", value or "").upper()


def account_status_from_event(event_kind):
    """Translate an Asaas account-status event into our local state."""
    kind = str(event_kind or "").upper()
    if kind == "ACCOUNT_STATUS_GENERAL_APPROVAL_APPROVED":
        return TenantPaymentAccount.Status.APPROVED
    if kind.endswith("_REJECTED"):
        return TenantPaymentAccount.Status.REJECTED
    if kind.endswith("_AWAITING_APPROVAL") or kind.endswith("_PENDING"):
        return TenantPaymentAccount.Status.PENDING
    return None


@transaction.atomic
def apply_subaccount_status(account_id, status, reason=""):
    """Persist a status transition without ever exposing the API key."""
    account = TenantPaymentAccount.objects.select_for_update().filter(
        provider_account_id=account_id
    ).first()
    if not account or status not in {
        TenantPaymentAccount.Status.PENDING,
        TenantPaymentAccount.Status.APPROVED,
        TenantPaymentAccount.Status.REJECTED,
    }:
        return None
    account.status = status
    fields = ["status", "updated_at"]
    if status == TenantPaymentAccount.Status.APPROVED:
        account.approved_at = account.approved_at or timezone.now()
        account.last_error = ""
        fields.extend(["approved_at", "last_error"])
    elif status == TenantPaymentAccount.Status.REJECTED:
        account.approved_at = None
        account.last_error = (reason or "O cadastro da subconta precisa ser revisado no Asaas.")[:500]
        fields.extend(["approved_at", "last_error"])
    account.save(update_fields=fields)
    return account


def configure_subaccount_webhook(api_key, email):
    """Provision account-status notifications when a public URL is configured."""
    url = str(getattr(settings, "ASAAS_WEBHOOK_URL", "") or "").strip()
    if not url:
        return False
    payload = {
        "name": "VemDeDelivery - aprovação da conta",
        "url": url,
        "email": email,
        "enabled": True,
        "interrupted": False,
        "apiVersion": 3,
        "authToken": settings.ASAAS_WEBHOOK_TOKEN,
        "sendType": "SEQUENTIALLY",
        "events": list(ACCOUNT_STATUS_EVENTS),
    }
    try:
        Asaas(api_key=api_key).request("POST", "/webhooks", json=payload)
        return True
    except BillingError as exc:
        # A periodic status reconciliation remains available if provisioning is
        # unavailable (for example, while DNS/TLS is being configured).
        log.warning("Não foi possível provisionar o webhook da subconta: %s", exc)
        return False


def sync_subaccount_status(account):
    """Fallback consultation used when Asaas retries or misses a webhook."""
    if not account.provider_account_id or not account.encrypted_api_key:
        return None
    data = Asaas(api_key=account.get_api_key()).request("GET", "/myAccount/status/")
    status_data = data.get("accountStatus") if isinstance(data.get("accountStatus"), dict) else data
    general = str((status_data or {}).get("general") or "").upper()
    mapping = {
        "APPROVED": TenantPaymentAccount.Status.APPROVED,
        "REJECTED": TenantPaymentAccount.Status.REJECTED,
        "PENDING": TenantPaymentAccount.Status.PENDING,
        "AWAITING_APPROVAL": TenantPaymentAccount.Status.PENDING,
    }
    local_status = mapping.get(general)
    if local_status:
        apply_subaccount_status(account.provider_account_id, local_status)
    return local_status


def sync_pending_subaccounts(limit=50):
    """Reconcile pending stores so approval does not depend on one delivery."""
    rows = TenantPaymentAccount.objects.filter(
        enabled=True,
        status=TenantPaymentAccount.Status.PENDING,
    ).exclude(provider_account_id="").exclude(encrypted_api_key="")[:limit]
    for account in rows:
        try:
            sync_subaccount_status(account)
        except (BillingError, ValueError):
            log.warning("Subconta aguardando consulta no Asaas. account_id=%s", account.pk)


def _disable_failed_activation(account, message):
    """Persist a failed activation attempt as OFF without losing accepted terms/data."""
    account.refresh_from_db()
    account.enabled = False
    account.status = TenantPaymentAccount.Status.ERROR
    account.last_error = str(message or "Falha ao solicitar a subconta.")[:500]
    account.save(update_fields=["enabled", "status", "last_error", "updated_at"])
    return account


def request_subaccount(account):
    """Create the Asaas subaccount once, keeping the returned API key encrypted."""
    try:
        if not account.terms_accepted:
            raise BillingError(
                "Confirme que está de acordo com as taxas e condições do Asaas antes de continuar."
            )
        if not configured():
            raise BillingError("Pagamentos online ainda não estão configurados.")
        if account.provider_account_id and account.encrypted_api_key:
            # Reativação de uma conta que já foi criada: não cria uma segunda
            # subconta e mantém o switch ligado.
            if not account.enabled:
                account.enabled = True
                account.save(update_fields=["enabled", "updated_at"])
            return account

        try:
            document = clean_asaas_document(account.document)
            mobile_phone = normalize_brazilian_phone(
                account.mobile_phone, required=True, mobile=True
            )
            phone = normalize_brazilian_phone(account.phone, mobile=False) if account.phone else ""
        except ValueError as exc:
            raise BillingError(str(exc)) from exc

        required = {
            "legal_name": account.legal_name,
            "email": account.email,
            "mobile_phone": mobile_phone,
            "income_value": account.income_value,
            "address": account.address,
            "address_number": account.address_number,
            "province": account.province,
            "postal_code": account.postal_code,
        }
        if any(value in (None, "") for value in required.values()):
            raise BillingError(
                "Complete os campos obrigatórios destacados antes de solicitar a ativação."
            )

        kind = document_kind(document)
        if kind == "CPF" and not account.birth_date:
            raise BillingError("Informe a data de nascimento do titular do CPF.")
        if kind == "CNPJ" and account.company_type not in COMPANY_TYPES:
            raise BillingError("Selecione um tipo de empresa aceito pelo Asaas.")

        postal_code = re.sub(r"\D", "", account.postal_code or "")
        if len(postal_code) != 8:
            raise BillingError("Informe um CEP válido com 8 dígitos.")
        if account.income_value is None or Decimal(account.income_value) <= 0:
            raise BillingError("O faturamento ou a renda mensal deve ser maior que zero.")

        payload = {
            "name": account.legal_name.strip(),
            "email": account.email.strip(),
            "cpfCnpj": document,
            "mobilePhone": mobile_phone,
            "incomeValue": float(account.income_value),
            "address": account.address.strip(),
            "addressNumber": account.address_number.strip(),
            "complement": (account.complement or "").strip(),
            "province": account.province.strip(),
            "postalCode": postal_code,
        }
        if phone:
            payload["phone"] = phone
        if kind == "CPF":
            payload["birthDate"] = account.birth_date.isoformat()
        elif kind == "CNPJ":
            payload["companyType"] = account.company_type

        data = Asaas().create_subaccount(payload)
        provider_id = valid_id(data.get("id"))
        wallet_id = valid_id(data.get("walletId"))
        api_key = data.get("apiKey")
        if not isinstance(api_key, str) or not api_key:
            raise BillingError("O Asaas não retornou a credencial da subconta.")

        with transaction.atomic():
            locked = TenantPaymentAccount.objects.select_for_update().get(pk=account.pk)
            locked.provider_account_id = provider_id
            locked.wallet_id = wallet_id
            locked.set_api_key(api_key)
            locked.enabled = True
            locked.status = TenantPaymentAccount.Status.PENDING
            locked.requested_at = timezone.now()
            locked.last_error = ""
            locked.save()

        configure_subaccount_webhook(api_key, account.email)
        return TenantPaymentAccount.objects.get(pk=account.pk)
    except BillingError as exc:
        # O aceite e os dados ficam salvos, mas o switch só permanece ligado
        # quando a solicitação realmente foi criada/reaproveitada com sucesso.
        if getattr(account, "pk", None):
            _disable_failed_activation(account, exc)
        raise


def online_payment_available(tenant):
    account = getattr(tenant, "payment_account", None)
    return bool(tenant.sale_mode == "online" and account and account.terms_accepted and account.is_ready)


def _checkout_url(identifier):
    host = "asaas.com" if environment() == "production" else "sandbox.asaas.com"
    return f"https://{host}/checkoutSession/show?id={identifier}"


def create_order_checkout(order, request):
    """Create an Asaas hosted Checkout in the tenant subaccount."""
    if order.payment_method not in ONLINE_METHODS:
        raise BillingError("Este pedido não utiliza pagamento online.")
    account = getattr(order.tenant, "payment_account", None)
    if not account or not account.is_ready:
        raise BillingError("O pagamento online desta loja ainda não foi aprovado pelo Asaas.")
    existing = OrderPayment.objects.filter(order=order).first()
    if existing and existing.checkout_url and existing.status == OrderPayment.Status.PENDING:
        return existing
    reference = f"vdd-order:{environment()}:{order.pk}:{order.public_token}"
    code = f"VDD-{order.pk}-{uuid.uuid4().hex[:8].upper()}"
    payment, _ = OrderPayment.objects.get_or_create(
        order=order,
        defaults={
            "tenant": order.tenant,
            "provider_account_id": account.provider_account_id,
            "external_reference": reference,
            "confirmation_code": code,
            "method": order.payment_method,
            "amount": order.total,
        },
    )
    if payment.checkout_url and payment.status == OrderPayment.Status.PENDING:
        return payment
    base = request.build_absolute_uri(reverse("orders:payment_return", args=[order.public_token]))
    body = {
        "billingTypes": [ONLINE_METHODS[order.payment_method]],
        "chargeTypes": ["DETACHED"],
        "minutesToExpire": 60,
        "externalReference": reference,
        "callback": {"successUrl": base, "cancelUrl": base, "expiredUrl": base},
        "items": [{
            "name": f"Pedido #{order.pk} - {order.tenant.name}",
            "description": "Pagamento online do pedido",
            "quantity": 1,
            "value": float(order.total),
        }],
    }
    try:
        api = Asaas(api_key=account.get_api_key())
        data = api.create_checkout(body)
        checkout_id = valid_id(data.get("id"))
        payment_url_value = payment_url(_checkout_url(checkout_id))
        payment.checkout_id = checkout_id
        payment.checkout_url = payment_url_value
        payment.status = OrderPayment.Status.PENDING
        payment.save(update_fields=["checkout_id", "checkout_url", "status", "updated_at"])
        return payment
    except BillingError as exc:
        payment.status = OrderPayment.Status.ERROR
        payment.save(update_fields=["status", "updated_at"])
        raise exc


@transaction.atomic
def apply_checkout_event(payment_id, checkout, event_kind):
    payment = OrderPayment.objects.select_for_update().select_related("order").get(checkout_id=payment_id)
    reference = checkout.get("externalReference")
    if reference != payment.external_reference:
        raise BillingError("Checkout não corresponde ao pedido.")
    value = checkout.get("value")
    if value not in (None, ""):
        try:
            valid_value = Decimal(str(value))
        except Exception:
            raise BillingError("Valor do checkout inválido.") from None
        if valid_value != payment.amount:
            raise BillingError("Valor do checkout não corresponde ao pedido.")
    status = str(checkout.get("status") or "").upper()
    if event_kind == "CHECKOUT_PAID" or status == "PAID":
        payment.status = OrderPayment.Status.PAID
        payment.paid_at = payment.paid_at or timezone.now()
    elif event_kind == "CHECKOUT_EXPIRED" or status == "EXPIRED":
        payment.status = OrderPayment.Status.EXPIRED
    elif event_kind == "CHECKOUT_CANCELED" or status == "CANCELED":
        payment.status = OrderPayment.Status.CANCELED
    payment.save(update_fields=["status", "paid_at", "updated_at"])
    return payment


def refresh_order_payment(payment):
    """Ask Asaas for the checkout status (redirects are not confirmation)."""
    account = TenantPaymentAccount.objects.filter(
        tenant=payment.tenant,
        provider_account_id=payment.provider_account_id,
    ).first()
    if not account or not account.is_ready or not payment.checkout_id:
        raise BillingError("Pagamento online ainda não está disponível para consulta.")
    checkout = Asaas(api_key=account.get_api_key()).get_checkout(payment.checkout_id)
    return apply_checkout_event(payment.checkout_id, checkout, "")
