"""Durable Pix intents, provider verification and transactional order creation."""

from decimal import Decimal
from datetime import timedelta
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone

from apps.billing.models import BillingEvent, TenantPaymentAccount
from apps.billing.online import online_payment_available
from apps.billing.provider import Asaas, BillingError, environment, valid_id
from apps.billing.secrets import decrypt_secret
from apps.integrations.models import (
    WhatsAppCheckout,
    WhatsAppCartReservation,
    WhatsAppOrderNotice,
)
from apps.orders import cart_service, inventory
from apps.orders.models import Order, OrderItem
from apps.orders.services import build_whatsapp_message


def reference(c):
    return f"vdd-wa:{c.environment}:{c.token}"


def snapshot_lines(c):
    ids = [i["product_id"] for i in c.snapshot["items"]]
    from apps.stores.models import Product

    products = {
        p.pk: p for p in Product.objects.filter(tenant=c.cart.tenant, pk__in=ids)
    }
    if len(products) != len(set(ids)):
        raise cart_service.CartError(
            "Um produto deste pedido foi removido; a loja precisa revisar o pagamento."
        )
    return [
        (SimpleNamespace(products=[products[i["product_id"]]]), i["quantity"])
        for i in c.snapshot["items"]
    ]


def confirm_checkout(c):
    from .checkout import reply

    if c.data["payment_flow"] == "online":
        if not online_payment_available(c.cart.tenant):
            raise cart_service.CartError(
                "O Pix online está indisponível. Escolha outra forma de pagamento."
            )
        account = c.cart.tenant.payment_account
        c.environment = environment()
        c.account_id = account.provider_account_id
        c.expires_at = timezone.now() + timedelta(minutes=30)
        c.status = "issuing"
        c.save()
        lines = snapshot_lines(c)
        products, demand = inventory.check_stock(
            lines,
            exclude_cart_id=c.cart_id,
            exclude_whatsapp_checkout_id=c.pk,
            lock=True,
        )
        for pk, count in demand.items():
            WhatsAppCartReservation.objects.create(
                checkout=c, product=products[pk], quantity=count
            )
        return reply(
            "Tudo certo! Vou gerar seu Pix. Pague em até 30 minutos.\n\nO pedido só será enviado à loja depois da confirmação do Asaas.",
            pix_checkout_id=c.pk,
        )
    create_order(c)
    return reply(
        f"Pedido *#{c.order_id}* confirmado! 🙂\n\n"
        + build_whatsapp_message(c.order)
        + "\n\nO resumo também será enviado para a loja."
    )


def api_for(c):
    if c.environment != environment():
        raise BillingError("Ambiente de pagamento diferente.")
    account = TenantPaymentAccount.objects.filter(
        tenant_id=c.cart.tenant_id, provider_account_id=c.account_id
    ).first()
    if not account or not account.encrypted_api_key:
        raise BillingError("Subconta indisponível para consulta.")
    return Asaas(api_key=account.get_api_key())


def validate_remote(c, data):
    try:
        valid = (
            data.get("id") == c.provider_id
            and data.get("externalReference") == reference(c)
            and data.get("billingType") == "PIX"
            and Decimal(str(data.get("value"))) == Decimal(c.snapshot["total"])
        )
    except Exception:
        valid = False
    if not valid:
        raise BillingError("Cobrança Pix não corresponde ao carrinho confirmado.")


def issue_pix(checkout_id):
    # Persist uncertainty BEFORE a POST. A timeout must never create another charge.
    with transaction.atomic():
        c = (
            WhatsAppCheckout.objects.select_for_update(of=("self",))
            .select_related("cart__tenant", "conversation")
            .get(pk=checkout_id)
        )
        if c.status not in {"issuing", "uncertain", "pending"}:
            return None
        api = api_for(c)
        may_create = c.status == "issuing"
        if may_create:
            c.status = "uncertain"
            c.save(update_fields=["status", "updated_at"])
    if not c.provider_id:
        found = api.find_payment(reference(c)).get("data", [])
        matches = [
            p
            for p in found
            if p.get("externalReference") == reference(c) and not p.get("deleted")
        ]
        if len(matches) > 1:
            raise BillingError("Cobrança precisa de revisão; não será duplicada.")
        if matches:
            payment = matches[0]
        elif may_create:
            customer_ref = f"vdd-wa-customer:{c.token}"
            customers = api.find_customer(customer_ref).get("data", [])
            customer = next(
                (
                    x
                    for x in customers
                    if x.get("externalReference") == customer_ref
                    and not x.get("deleted")
                ),
                None,
            )
            if not customer:
                customer = api.create_customer(
                    {
                        "name": c.data["customer_name"],
                        "cpfCnpj": decrypt_secret(c.data["document_encrypted"]),
                        "mobilePhone": c.conversation.phone_number.removeprefix("55"),
                        "externalReference": customer_ref,
                        "notificationDisabled": True,
                    }
                )
            payment = api.create_payment(
                {
                    "customer": valid_id(customer.get("id")),
                    "billingType": "PIX",
                    "value": float(Decimal(c.snapshot["total"])),
                    "dueDate": timezone.localdate().isoformat(),
                    "externalReference": reference(c),
                    "description": f"Pedido WhatsApp - {c.cart.tenant.name}"[:500],
                }
            )
        else:
            raise BillingError(
                "A emissão ainda não foi confirmada. A loja precisa conferir a cobrança antes de uma nova tentativa."
            )
        with transaction.atomic():
            c = (
                WhatsAppCheckout.objects.select_for_update(of=("self",))
                .select_related("cart__tenant", "conversation")
                .get(pk=checkout_id)
            )
            c.provider_id = valid_id(payment.get("id"))
            validate_remote(c, payment)
            c.status = "pending"
            c.data.pop("document_encrypted", None)
            c.save()
            # Recover a webhook received before the provider ID was committed.
            BillingEvent.objects.filter(
                payment_id=c.provider_id,
                environment=c.environment,
                kind__startswith="PAYMENT_",
            ).update(processed_at=None)
    qr = api.pix(c.provider_id)
    if (
        not isinstance(qr.get("payload"), str)
        or not qr["payload"]
        or not isinstance(qr.get("encodedImage"), str)
    ):
        raise BillingError("QR Code ainda indisponível.")
    return qr


@transaction.atomic
def create_order(c):
    if c.order_id:
        return c.order
    paid = c.data["payment_flow"] == "online"
    if paid and not c.paid_at:
        raise BillingError("Pagamento ainda não confirmado.")
    s = c.snapshot
    order = Order.objects.create(
        tenant=c.cart.tenant,
        checkout_token=c.token,
        source_cart_id=c.cart_id,
        subtotal=s["subtotal"],
        delivery_fee=s["delivery_fee"],
        total=s["total"],
        **s["fields"],
    )
    for item in s["items"]:
        OrderItem.objects.create(order=order, **item)
    inventory.consume(order, snapshot_lines(c), exclude_whatsapp_checkout_id=c.pk)
    order.whatsapp_opened_at = timezone.now()
    order.save(update_fields=["whatsapp_opened_at"])
    c.order = order
    c.status = "completed"
    c.data.pop("document_encrypted", None)
    c.save()
    c.reservations.all().delete()
    c.cart.items.all().delete()
    # Save outbox in the same transaction as the order. Broker outages cannot lose it.
    message = build_whatsapp_message(order)
    if paid:
        message += f"\n\n✅ *Pix online pago e validado pelo Asaas.*\nReferência: {c.provider_id}\n*Não cobrar novamente.*"
    else:
        message += "\n\n*Pagamento na entrega/retirada — ainda não pago.*"
    tenant = c.cart.tenant
    order_recipient = tenant.whatsapp_order_number or tenant.whatsapp_number
    # Preserve the customer receipt and route the store copy to the optional
    # operations number. A set deduplicates when both destinations are equal.
    for recipient in {c.conversation.phone_number, order_recipient}:
        WhatsAppOrderNotice.objects.get_or_create(
            checkout=c, recipient=recipient, defaults={"text": message}
        )
    return order


def apply_pix_event(checkout_id, event):
    """Only an authenticated, persisted webhook can release an online order."""
    c = WhatsAppCheckout.objects.select_related("cart__tenant").get(pk=checkout_id)
    if (
        event.payment_id != c.provider_id
        or event.environment != c.environment
        or not event.kind.startswith("PAYMENT_")
    ):
        raise BillingError("Evento não corresponde ao Pix.")
    remote = api_for(c).get_payment(c.provider_id)
    fulfillment_error = None
    with transaction.atomic():
        c = (
            WhatsAppCheckout.objects.select_for_update(of=("self",))
            .select_related("cart__tenant", "conversation")
            .get(pk=checkout_id)
        )
        validate_remote(c, remote)
        status = remote.get("status")
        if status in {"RECEIVED", "CONFIRMED"}:
            c.paid_at = c.paid_at or timezone.now()
            c.save(update_fields=["paid_at", "updated_at"])
            try:
                create_order(c)
            except cart_service.CartError as exc:
                c.status = "paid_waiting"
                c.save(update_fields=["status", "updated_at"])
                fulfillment_error = str(exc)
        elif status in {
            "REFUNDED",
            "CHARGEBACK_REQUESTED",
            "CHARGEBACK_DISPUTE",
            "AWAITING_CHARGEBACK_REVERSAL",
        }:
            # Never silently mark a refund as an unpaid cart or release it again.
            c.status = "payment_review"
            c.save(update_fields=["status", "updated_at"])
        elif event.kind in {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"} and status in {
            "PENDING",
            "OVERDUE",
        }:
            raise BillingError(
                "Confirmação ainda não disponível na consulta; reprocessar webhook."
            )
        elif remote.get("deleted") or status in {"DELETED", "CANCELED"}:
            if not c.order_id:
                c.status = "cancelled"
                c.data.pop("document_encrypted", None)
                c.save()
                c.reservations.all().delete()
    if fulfillment_error:
        raise BillingError(fulfillment_error)
    return c


def cancel_payment(c):
    from .checkout import reply

    if not c.provider_id:
        return reply(
            "A emissão do Pix ainda precisa ser conferida. Não vou gerar outra cobrança. Escreva *atendente* para a loja ajudar."
        )
    try:
        api = api_for(c)
        remote = api.get_payment(c.provider_id)
        validate_remote(c, remote)
        if remote.get("status") in {"RECEIVED", "CONFIRMED"}:
            return reply(
                "O Asaas já informa o pagamento. Estou aguardando o processamento do webhook para confirmar seu pedido."
            )
        if remote.get("status") not in {"PENDING", "OVERDUE"}:
            return reply(
                "O pagamento precisa de conferência da loja antes de cancelar. Escreva *atendente*."
            )
        deleted = api.request("DELETE", "/payments/" + valid_id(c.provider_id))
        if deleted.get("deleted") is not True:
            raise BillingError("Cancelamento não confirmado.")
    except BillingError:
        return reply(
            "Ainda não consegui confirmar o cancelamento no Asaas. Seu carrinho foi preservado; tente novamente em instantes.",
            [("cancel", "Tentar cancelar")],
        )
    c.status = "cancelled"
    c.data.pop("document_encrypted", None)
    c.reservations.all().delete()
    return reply(
        "Pix cancelado no Asaas. Para montar outro carrinho, escreva *novo pedido*."
    )
