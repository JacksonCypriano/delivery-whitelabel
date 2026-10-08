"""Operational order workflow for Package 13.

This module is the authoritative state machine used by the React merchant panel.
It deliberately keeps pricing, stock, delivery and WhatsApp provider concerns in
existing backend services instead of moving business rules into React.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.stores.models import CustomizationGroup, HalfProduct, Product
from apps.tenants.delivery import resolve_delivery

from . import cart_service, inventory
from .choices import OrderSource, Status, StatusEventSource
from .models import (
    Order,
    OrderItem,
    OrderNotificationSettings,
    OrderStatusEvent,
    OrderStatusNotification,
)


class OrderOperationError(ValueError):
    pass


# Explicit transitions keep accidental backwards jumps out of the operational
# panel. Cancellation is intentionally limited to pre-preparation states because
# the current stock return routine restores already deducted stock.
BASE_TRANSITIONS = {
    Status.PENDING: (Status.CONFIRMED, Status.CANCELLED),
    Status.CONFIRMED: (Status.PREPARING, Status.READY, Status.CANCELLED),
    Status.PREPARING: (Status.READY,),
    Status.READY: (Status.OUT_FOR_DELIVERY, Status.DELIVERED),
    Status.READY_FOR_PICKUP: (Status.DELIVERED,),
    Status.OUT_FOR_DELIVERY: (Status.DELIVERED,),
    Status.DELIVERED: (),
    Status.CANCELLED: (),
}

STATUS_LABELS = dict(Status.choices)
SOURCE_LABELS = dict(OrderSource.choices)


def operational_order_q():
    """Orders that have actually reached the merchant operation.

    Web checkout creates a short-lived review draft before the customer commits
    stock/opens WhatsApp. Those drafts must never leak into the operational board
    or status automation. Manual orders are operational immediately.
    """
    return Q(source=OrderSource.MANUAL) | Q(whatsapp_opened_at__isnull=False)


def _settings_for(tenant):
    settings, _ = OrderNotificationSettings.objects.get_or_create(tenant=tenant)
    return settings


def allowed_transitions(order: Order):
    allowed = list(BASE_TRANSITIONS.get(order.status, ()))
    if order.delivery_type == "pickup":
        allowed = [Status.READY_FOR_PICKUP if status == Status.READY else status for status in allowed]
        if Status.OUT_FOR_DELIVERY in allowed:
            allowed.remove(Status.OUT_FOR_DELIVERY)
    return allowed


def _prep_minutes(value, default=None):
    if value in (None, ""):
        return default
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise OrderOperationError("Informe um prazo em minutos inteiros.")
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        raise OrderOperationError("Informe um tempo de preparo válido.") from None
    if not 5 <= minutes <= 240:
        raise OrderOperationError("O tempo de preparo deve ficar entre 5 e 240 minutos.")
    return minutes


def build_status_message(order: Order, target_status: str, *, include_estimate=True):
    number = f"#{order.pk}"
    estimate = ""
    if include_estimate and order.estimated_ready_at and target_status in {
        Status.CONFIRMED,
        Status.PREPARING,
    }:
        local = timezone.localtime(order.estimated_ready_at)
        estimate = f"\nPrevisão para ficar pronto: *{local:%H:%M}*."

    if target_status == Status.CONFIRMED:
        return f"✅ Seu pedido {number} foi confirmado pela loja.{estimate}"
    if target_status == Status.PREPARING:
        return f"👨‍🍳 Seu pedido {number} está em preparo.{estimate}"
    if target_status == Status.READY_FOR_PICKUP:
        return f"✅ Seu pedido {number} está pronto para retirada! Você já pode vir buscar na loja."
    if target_status == Status.READY:
        if order.delivery_type == "pickup":
            return f"✅ Seu pedido {number} está pronto para retirada."
        return f"✅ Seu pedido {number} está pronto e aguardando a saída para entrega."
    if target_status == Status.OUT_FOR_DELIVERY:
        return f"🚚 Seu pedido {number} saiu para entrega. Daqui a pouco ele chega até você."
    if target_status == Status.DELIVERED:
        return f"✅ Seu pedido {number} foi marcado como entregue. Obrigado por comprar com a gente! 😊"
    if target_status == Status.CANCELLED:
        return f"❌ Seu pedido {number} foi cancelado pela loja. Se precisar de ajuda, responda por aqui."
    return ""


def notification_enabled(settings: OrderNotificationSettings, status: str):
    if not settings.enabled:
        return False
    mapping = {
        Status.CONFIRMED: settings.notify_confirmed,
        Status.PREPARING: settings.notify_preparing,
        Status.READY: settings.notify_ready,
        Status.READY_FOR_PICKUP: settings.notify_ready,
        Status.OUT_FOR_DELIVERY: settings.notify_out_for_delivery,
        Status.DELIVERED: settings.notify_delivered,
        Status.CANCELLED: settings.notify_cancelled,
    }
    return bool(mapping.get(status, False))


def record_initial_event(
    order: Order,
    *,
    actor=None,
    source: str = StatusEventSource.SYSTEM,
    note: str = "Pedido criado.",
):
    """Persist the first operational breadcrumb without sending a status notice."""
    return OrderStatusEvent.objects.get_or_create(
        order=order,
        tenant=order.tenant,
        from_status="",
        to_status=order.status,
        defaults={
            "actor": actor if getattr(actor, "is_authenticated", False) else None,
            "source": source,
            "note": str(note or "")[:255],
        },
    )[0]


def _queue_notification(event: OrderStatusEvent):
    order = event.order
    settings = _settings_for(order.tenant)
    phone = re.sub(r"\D", "", order.customer_phone or "")
    if not phone or not notification_enabled(settings, event.to_status):
        return None
    if event.metadata.get("send_notification") is False:
        return None
    text = event.metadata.get("message") or build_status_message(order, event.to_status)
    if not text:
        return None
    notice, _ = OrderStatusNotification.objects.get_or_create(
        event=event,
        defaults={
            "tenant": order.tenant,
            "recipient": phone,
            "text": text,
        },
    )
    return notice


def _after_commit(order_id: int, notification_id: int | None = None):
    # Order saves are broadcast by ``apps.orders.signals`` after commit.
    # This callback only gives the Celery outbox a fast path; beat remains the
    # recovery path if the broker is temporarily unavailable.
    if notification_id:
        # Broker failures cannot lose the outbox row. The periodic worker scans
        # pending rows as a recovery path.
        try:
            from .tasks import deliver_order_status_notification

            deliver_order_status_notification.delay(notification_id)
        except Exception:
            pass


def transition_order(
    *,
    order_id: int,
    tenant,
    target_status: str,
    actor=None,
    prep_minutes=None,
    note: str = "",
    source: str = StatusEventSource.PANEL,
    fulfillment_minutes=None,
    message=None,
    complement="",
    send_notification=None,
):
    if target_status not in Status.values:
        raise OrderOperationError("Status de pedido inválido.")

    if send_notification is not None and not isinstance(send_notification, bool):
        raise OrderOperationError("A opção de envio deve ser verdadeira ou falsa.")
    if message is not None and (not isinstance(message, str) or len(message) > 2000):
        raise OrderOperationError("A mensagem deve ter no máximo 2000 caracteres.")
    if not isinstance(complement, str) or len(complement) > 500:
        raise OrderOperationError("O complemento deve ter no máximo 500 caracteres.")
    minutes = _prep_minutes(prep_minutes)
    fulfillment = _prep_minutes(fulfillment_minutes)
    with transaction.atomic():
        settings = _settings_for(tenant)
        if send_notification is False and not settings.allow_skip_notification:
            raise OrderOperationError("Esta loja exige os avisos de status configurados.")
        if target_status == Status.CANCELLED:
            if not Order.objects.filter(
                pk=order_id, tenant=tenant, abandoned_at__isnull=True
            ).filter(operational_order_q()).exists():
                raise Order.DoesNotExist
            changed, previous, order = inventory.cancel_with_previous(
                order_id,
                tenant,
                allowed_statuses={Status.PENDING, Status.CONFIRMED},
            )
            if not changed:
                return order, None
        else:
            order = (
                Order.objects.select_for_update()
                .select_related("tenant")
                .filter(pk=order_id, tenant=tenant, abandoned_at__isnull=True)
                .filter(operational_order_q())
                .get()
            )
            if target_status == order.status:
                return order, None
            # Old clients may still submit ready for pickup; persist the real new state.
            if target_status == Status.READY and order.delivery_type == "pickup":
                target_status = Status.READY_FOR_PICKUP
            previous = order.status
            if target_status == previous:
                return order, None
            allowed = allowed_transitions(order)
            if target_status not in allowed:
                current = STATUS_LABELS.get(previous, previous)
                target = STATUS_LABELS.get(target_status, target_status)
                raise OrderOperationError(
                    f"Não é possível mudar o pedido de {current} para {target}."
                )

            settings = _settings_for(tenant)
            minutes = _prep_minutes(prep_minutes)
            if target_status in {Status.CONFIRMED, Status.PREPARING}:
                if minutes is None and order.estimated_ready_at is None:
                    minutes = settings.default_prep_minutes
                if minutes is not None:
                    order.estimated_ready_at = timezone.now() + timedelta(minutes=minutes)

            if target_status == Status.OUT_FOR_DELIVERY:
                fulfillment = fulfillment or settings.default_delivery_minutes
            elif order.delivery_type == "pickup" and target_status in {Status.CONFIRMED, Status.PREPARING}:
                if fulfillment is None and order.estimated_fulfillment_at is None:
                    fulfillment = settings.default_pickup_minutes
            if fulfillment is not None:
                order.estimated_fulfillment_at = timezone.now() + timedelta(minutes=fulfillment)
            if target_status == Status.READY_FOR_PICKUP:
                order.estimated_fulfillment_at = timezone.now()

            order.status = target_status
            order.status_updated_at = timezone.now()
            update_fields = ["status", "status_updated_at", "estimated_fulfillment_at"]
            if target_status in {Status.CONFIRMED, Status.PREPARING}:
                update_fields.append("estimated_ready_at")
            order.save(update_fields=update_fields)

        text = (message or "").strip() or build_status_message(order, target_status)
        if (message or "").strip() and order.estimated_ready_at and target_status in {Status.CONFIRMED, Status.PREPARING}:
            local = timezone.localtime(order.estimated_ready_at)
            text += f"\nPrevisão para ficar pronto: {local:%H:%M}."
        if order.estimated_fulfillment_at and target_status in {Status.CONFIRMED, Status.PREPARING, Status.OUT_FOR_DELIVERY}:
            local = timezone.localtime(order.estimated_fulfillment_at)
            label = "retirada" if order.delivery_type == "pickup" else "entrega"
            text += f"\nPrevisão de {label}: {local:%H:%M}."
        if complement.strip():
            text += "\n" + complement.strip()
        event = OrderStatusEvent.objects.create(
            metadata={
                "prep_minutes": minutes, "fulfillment_minutes": fulfillment,
                "estimated_ready_at": order.estimated_ready_at.isoformat() if order.estimated_ready_at else None,
                "estimated_fulfillment_at": order.estimated_fulfillment_at.isoformat() if order.estimated_fulfillment_at else None,
                "send_notification": send_notification, "message": text,
            },
            order=order,
            tenant=tenant,
            from_status=previous,
            to_status=target_status,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            source=source,
            note=str(note or "")[:255],
        )
        notice = _queue_notification(event)
        transaction.on_commit(
            lambda oid=order.pk, nid=(notice.pk if notice else None): _after_commit(
                oid, nid
            )
        )
        return order, event


def update_estimate(*, order_id: int, tenant, minutes, actor=None):
    minutes = _prep_minutes(minutes)
    if minutes is None:
        raise OrderOperationError("Informe o prazo em minutos.")
    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .filter(pk=order_id, tenant=tenant, abandoned_at__isnull=True)
            .filter(operational_order_q())
            .get()
        )
        if order.status in {Status.DELIVERED, Status.CANCELLED}:
            raise OrderOperationError("Este pedido já foi finalizado.")
        order.estimated_ready_at = timezone.now() + timedelta(minutes=minutes)
        order.status_updated_at = timezone.now()
        order.save(update_fields=["estimated_ready_at", "status_updated_at"])
        event = OrderStatusEvent.objects.create(
            order=order,
            tenant=tenant,
            from_status=order.status,
            to_status=order.status,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            source=StatusEventSource.PANEL,
            note=f"Previsão de preparo ajustada para {minutes} minuto(s).",
            metadata={"prep_minutes": minutes, "estimated_ready_at": order.estimated_ready_at.isoformat()},
        )
        transaction.on_commit(lambda oid=order.pk: _after_commit(oid))
        return order, event


def _image_url(product):
    try:
        return product.get_primary_image() or ""
    except Exception:
        return ""


def manual_catalog(tenant):
    today = timezone.localdate().weekday()
    products = list(
        Product.objects.filter(tenant=tenant, is_available=True)
        .select_related("category")
        .prefetch_related("images")
        .order_by("category__display_order", "category__name", "name")
    )
    products = [
        p
        for p in products
        if (not p.available_days or today in p.available_days)
        and (p.stock is None or p.stock > 0)
    ]
    categories = {}
    for p in products:
        categories.setdefault(p.category_id, {"id": p.category_id, "name": p.category.name})

    groups = (
        CustomizationGroup.objects.filter(
            tenant=tenant,
            category_id__in=categories,
            is_active=True,
        )
        .select_related("label", "category")
        .prefetch_related("options")
        .order_by("category_id", "pk")
    )
    groups_by_category = {}
    for group in groups:
        rows = [
            {
                "id": option.pk,
                "name": option.name,
                "description": option.description,
                "price": str(option.price),
            }
            for option in group.options.all()
            if option.is_available and option.tenant_id == tenant.pk
        ]
        groups_by_category.setdefault(str(group.category_id), []).append(
            {
                "id": group.pk,
                "name": group.name,
                "apply_to": group.apply_to,
                "min_options": group.min_options,
                "max_options": group.max_options,
                "options": rows,
            }
        )

    half_ids = set(
        HalfProduct.objects.filter(
            tenant=tenant,
            product_id__in=[p.pk for p in products],
            is_active=True,
        ).values_list("product_id", flat=True)
    )
    return {
        "products": [
            {
                "id": p.pk,
                "category_id": p.category_id,
                "category": p.category.name,
                "name": p.name,
                "price": str(cart_service.product_price(p)),
                "stock": None if p.stock is None else str(p.stock),
                "min_qty": p.min_order_qty,
                "max_qty": p.max_order_qty,
                "prep_time": p.prep_time,
                "image": _image_url(p),
                "half_enabled": p.pk in half_ids,
            }
            for p in products
        ],
        "categories": list(categories.values()),
        "groups": groups_by_category,
        "accepts_delivery": tenant.accepts_delivery,
        "accepts_pickup": tenant.accepts_pickup,
    }


def _manual_lines(tenant, raw_items):
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 50:
        raise OrderOperationError("Inclua de 1 a 50 itens no pedido.")
    lines = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise OrderOperationError("Há um item inválido no pedido.")
        try:
            quote = cart_service.quote(tenant, raw)
            count = cart_service.check_quantity(quote, raw.get("quantity", 1))
        except cart_service.CartError as exc:
            raise OrderOperationError(str(exc)) from exc
        lines.append((quote, count))
    try:
        subtotal = cart_service.validate_totals(lines)
    except cart_service.CartError as exc:
        raise OrderOperationError(str(exc)) from exc
    return lines, subtotal


def quote_manual_order(*, tenant, items, delivery_type="pickup", city="", neighborhood=""):
    lines, subtotal = _manual_lines(tenant, items)
    delivery = resolve_delivery(
        tenant=tenant,
        delivery_type=delivery_type,
        city=city,
        neighborhood=neighborhood,
    )
    if not delivery["available"]:
        raise OrderOperationError(delivery["message"])
    fee = Decimal(delivery["fee"])
    return {
        "subtotal": subtotal,
        "delivery_fee": fee,
        "total": cart_service.money(subtotal + fee),
        "lines": lines,
    }


def create_manual_order(*, tenant, data, actor=None):
    customer_name = str(data.get("customer_name") or "Cliente do balcão").strip()[:150]
    raw_phone = str(data.get("customer_phone") or "").strip()
    customer_phone = ""
    if raw_phone:
        from apps.integrations.whatsapp.service import normalize_br_phone

        try:
            customer_phone = normalize_br_phone(raw_phone)
        except ValueError as exc:
            raise OrderOperationError("Informe um WhatsApp válido com DDD ou deixe o campo vazio.") from exc
    delivery_type = str(data.get("delivery_type") or "pickup")
    if delivery_type not in {"pickup", "delivery"}:
        raise OrderOperationError("Forma de recebimento inválida.")
    if delivery_type == "delivery" and not tenant.accepts_delivery:
        raise OrderOperationError("Esta loja não aceita pedidos para entrega.")
    if delivery_type == "pickup" and not tenant.accepts_pickup:
        raise OrderOperationError("Esta loja não aceita retirada.")

    quoted = quote_manual_order(
        tenant=tenant,
        items=data.get("items"),
        delivery_type=delivery_type,
        city=data.get("delivery_city", ""),
        neighborhood=data.get("delivery_neighborhood", ""),
    )
    payment_method = str(data.get("payment_method") or "pix")
    if payment_method not in {"cash", "credit_card", "debit_card", "pix"}:
        raise OrderOperationError("Forma de pagamento inválida.")
    change_for = str(data.get("payment_change_for") or "").strip()[:30]

    address = {
        "delivery_zip_code": str(data.get("delivery_zip_code") or "").strip()[:9],
        "delivery_street": str(data.get("delivery_street") or "").strip()[:255],
        "delivery_number": str(data.get("delivery_number") or "").strip()[:20],
        "delivery_complement": str(data.get("delivery_complement") or "").strip()[:100],
        "delivery_neighborhood": str(data.get("delivery_neighborhood") or "").strip()[:100],
        "delivery_city": str(data.get("delivery_city") or "").strip()[:100],
        "delivery_state": str(data.get("delivery_state") or "").strip().upper()[:2],
        "delivery_reference": str(data.get("delivery_reference") or "").strip()[:255],
    }
    if delivery_type == "delivery":
        required = ["delivery_street", "delivery_number", "delivery_neighborhood", "delivery_city"]
        if any(not address[name] for name in required):
            raise OrderOperationError("Preencha rua, número, bairro e cidade para a entrega.")

    with transaction.atomic():
        order = Order.objects.create(
            tenant=tenant,
            customer_name=customer_name,
            customer_phone=customer_phone,
            status=Status.PENDING,
            source=OrderSource.MANUAL,
            subtotal=quoted["subtotal"],
            delivery_fee=quoted["delivery_fee"],
            total=quoted["total"],
            delivery_type=delivery_type,
            payment_flow="in_person",
            payment_method=payment_method,
            payment_change_for=change_for if payment_method == "cash" else "",
            **(address if delivery_type == "delivery" else {}),
        )
        for quote, count in quoted["lines"]:
            OrderItem.objects.create(
                order=order,
                product=quote.product,
                name=quote.name,
                price=quote.price,
                quantity=count,
                combination_details=quote.details,
                product_key=quote.key,
                notes=quote.notes,
            )
        try:
            inventory.consume(order, quoted["lines"])
        except cart_service.CartError as exc:
            raise OrderOperationError(str(exc)) from exc

        record_initial_event(
            order,
            actor=actor,
            source=StatusEventSource.PANEL,
            note="Pedido manual criado pelo painel.",
        )
        transaction.on_commit(lambda oid=order.pk: _after_commit(oid))
        return order


def _canonical_customer_phone(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("55") and len(digits) in {12, 13}:
        return digits
    if len(digits) in {10, 11}:
        return f"55{digits}"
    return ""


def customer_status_reply(*, tenant, phone, question=""):
    """Return a deterministic status answer for the caller's own recent order."""
    sender = _canonical_customer_phone(phone)
    if not sender:
        return None

    candidate_ids = [int(x) for x in re.findall(r"(?:#|pedido\s*)(\d{1,12})", str(question or ""), flags=re.I)]
    qs = (
        Order.objects.filter(tenant=tenant, abandoned_at__isnull=True)
        .filter(operational_order_q())
        .only(
            "id", "customer_phone", "status", "estimated_ready_at",
            "delivery_type", "created_at",
        )
        .order_by("-created_at", "-pk")
    )
    if candidate_ids:
        qs = qs.filter(pk__in=candidate_ids)
    else:
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=7))[:30]

    order = None
    for row in qs:
        saved = _canonical_customer_phone(row.customer_phone)
        if saved and saved == sender:
            order = row
            break
    if order is None:
        return (
            "Não encontrei um pedido recente vinculado a este WhatsApp. "
            "Se você fez o pedido com outro número, fale com a equipe da loja por aqui."
        )

    label = STATUS_LABELS.get(order.status, order.status)
    if order.status == Status.PENDING:
        text = f"Seu pedido #{order.pk} foi recebido e está aguardando confirmação da loja."
    elif order.status == Status.CONFIRMED:
        text = f"Seu pedido #{order.pk} está *confirmado* ✅."
    elif order.status == Status.PREPARING:
        text = f"Seu pedido #{order.pk} está *em preparo* 👨‍🍳."
    elif order.status in {Status.READY, Status.READY_FOR_PICKUP}:
        text = (
            f"Seu pedido #{order.pk} está *pronto para retirada* ✅."
            if order.delivery_type == "pickup"
            else f"Seu pedido #{order.pk} está *pronto* e aguardando sair para entrega ✅."
        )
    elif order.status == Status.OUT_FOR_DELIVERY:
        text = f"Seu pedido #{order.pk} *saiu para entrega* 🚚."
    elif order.status == Status.DELIVERED:
        text = f"Seu pedido #{order.pk} consta como *entregue* ✅."
    elif order.status == Status.CANCELLED:
        text = f"Seu pedido #{order.pk} consta como *cancelado*."
    else:
        text = f"Seu pedido #{order.pk} está com status: *{label}*."

    if order.estimated_ready_at and order.status in {Status.CONFIRMED, Status.PREPARING}:
        local = timezone.localtime(order.estimated_ready_at)
        text += f"\nPrevisão para ficar pronto: *{local:%H:%M}*."
    if order.estimated_fulfillment_at and order.status in {Status.CONFIRMED, Status.PREPARING, Status.OUT_FOR_DELIVERY}:
        local = timezone.localtime(order.estimated_fulfillment_at)
        label = "retirada" if order.delivery_type == "pickup" else "entrega"
        text += f"\nPrevisão de {label}: *{local:%H:%M}*."
    return text
