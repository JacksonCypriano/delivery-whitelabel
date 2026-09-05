"""Online order payments routed to the store's Asaas subaccount."""
import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import OrderPayment, TenantPaymentAccount
from .provider import Asaas, BillingError, configured, environment, payment_url, valid_id


ONLINE_METHODS = {"pix": "PIX", "credit_card": "CREDIT_CARD"}


def _clean_document(value):
    return re.sub(r"[^0-9A-Za-z]", "", value or "").upper()


def request_subaccount(account):
    """Create the Asaas subaccount once, keeping the returned API key encrypted."""
    if not account.terms_accepted:
        raise BillingError("Confirme que está de acordo com as taxas e condições do Asaas antes de continuar.")
    if not configured():
        raise BillingError("Pagamentos online ainda não estão configurados.")
    if account.provider_account_id and account.encrypted_api_key:
        return account
    required = {
        "legal_name": account.legal_name,
        "document": account.document,
        "email": account.email,
        "mobile_phone": account.mobile_phone,
        "income_value": account.income_value,
        "address": account.address,
        "address_number": account.address_number,
        "province": account.province,
        "postal_code": account.postal_code,
    }
    if len(_clean_document(account.document)) == 11:
        required["birth_date"] = account.birth_date
    if any(value in (None, "") for value in required.values()):
        raise BillingError("Complete os dados financeiros da loja antes de solicitar a ativação.")
    payload = {
        "name": account.legal_name,
        "email": account.email,
        "cpfCnpj": _clean_document(account.document),
        "mobilePhone": re.sub(r"\D", "", account.mobile_phone),
        "incomeValue": float(account.income_value),
        "address": account.address,
        "addressNumber": account.address_number,
        "complement": account.complement,
        "province": account.province,
        "postalCode": re.sub(r"\D", "", account.postal_code),
    }
    if account.phone:
        payload["phone"] = re.sub(r"\D", "", account.phone)
    if account.birth_date:
        payload["birthDate"] = account.birth_date.isoformat()
    if account.company_type:
        payload["companyType"] = account.company_type
    try:
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
            return locked
    except BillingError as exc:
        TenantPaymentAccount.objects.filter(pk=account.pk).update(status=TenantPaymentAccount.Status.ERROR, last_error=str(exc)[:500])
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
