"""Operational order API used by the React merchant panel (Package 13)."""

from __future__ import annotations

from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from rest_framework.response import Response

from apps.integrations.models import WhatsAppCheckout
from apps.orders.choices import OrderSource, Status
from apps.orders.models import (
    Order,
    OrderItem,
    OrderNotificationSettings,
)
from apps.orders.operations import (
    OrderOperationError,
    STATUS_LABELS,
    allowed_transitions,
    create_manual_order,
    manual_catalog,
    quote_manual_order,
    transition_order,
    update_estimate,
)

from .api import MerchantAPI
from .schema import value


def _payment_info(order, whatsapp_checkout=None):
    if order.payment_flow == "in_person":
        return {
            "status": "in_person",
            "label": "Pagamento na entrega/retirada",
            "paid": False,
        }
    payment = getattr(order, "online_payment", None)
    if payment is not None:
        return {
            "status": payment.status,
            "label": payment.get_status_display(),
            "paid": payment.status == "PAID",
        }
    if whatsapp_checkout is not None:
        paid = bool(whatsapp_checkout.paid_at)
        return {
            "status": whatsapp_checkout.status,
            "label": "Pix pago e validado" if paid else "Aguardando confirmação",
            "paid": paid,
        }
    return {"status": "pending", "label": "Aguardando confirmação", "paid": False}


def _order_card(order, whatsapp_checkout=None):
    now = timezone.now()
    estimate = order.estimated_ready_at
    return {
        "id": order.pk,
        "customer_name": order.customer_name or "Cliente",
        "customer_phone": order.customer_phone,
        "status": order.status,
        "status_label": STATUS_LABELS.get(order.status, order.status),
        "source": order.source,
        "source_label": dict(OrderSource.choices).get(order.source, order.source),
        "delivery_type": order.delivery_type,
        "delivery_label": order.delivery_type_label,
        "payment": _payment_info(order, whatsapp_checkout),
        "payment_label": order.payment_label,
        "total": str(order.total),
        "created_at": value(order.created_at),
        "status_updated_at": value(order.status_updated_at),
        "estimated_ready_at": value(estimate),
        "late": bool(
            estimate
            and estimate < now
            and order.status not in {Status.READY, Status.OUT_FOR_DELIVERY, Status.DELIVERED, Status.CANCELLED}
        ),
        "items": [
            {
                "id": item.pk,
                "name": item.name,
                "quantity": item.quantity,
                "price": str(item.price),
                "notes": item.notes,
            }
            for item in list(order.items.all())[:6]
        ],
        "item_count": sum(item.quantity for item in order.items.all()),
        "allowed_transitions": [
            {"value": status, "label": STATUS_LABELS[status]}
            for status in allowed_transitions(order)
        ],
    }


def _base_queryset(tenant):
    return (
        Order.objects.filter(tenant=tenant, abandoned_at__isnull=True)
        .filter(Q(source=OrderSource.MANUAL) | Q(whatsapp_opened_at__isnull=False))
        .select_related("online_payment")
        .prefetch_related(Prefetch("items", queryset=OrderItem.objects.order_by("pk")))
    )


class OrdersBoard(MerchantAPI):
    def get(self, request):
        base = _base_queryset(request.tenant)
        active_statuses = [
            Status.PENDING,
            Status.CONFIRMED,
            Status.PREPARING,
            Status.READY,
            Status.OUT_FOR_DELIVERY,
        ]
        # Keep every operational order visible regardless of volume. Only the
        # completed/cancelled history is capped, otherwise a busy store could
        # hide the newest orders behind an arbitrary global limit.
        active_rows = list(
            base.filter(status__in=active_statuses).order_by("created_at", "pk")
        )
        finished_rows = list(
            base.filter(status__in=[Status.DELIVERED, Status.CANCELLED])
            .order_by("-created_at", "-pk")[:50]
        )
        rows = active_rows + finished_rows
        order_ids = [row.pk for row in rows]
        wa = {
            row.order_id: row
            for row in WhatsAppCheckout.objects.filter(order_id__in=order_ids).only(
                "order_id", "status", "paid_at"
            )
        }
        cards = [_order_card(row, wa.get(row.pk)) for row in rows]
        columns = [
            {
                "status": status,
                "label": "Novos" if status == Status.PENDING else STATUS_LABELS[status],
                "orders": [card for card in cards if card["status"] == status],
            }
            for status in active_statuses
        ]
        finished = [
            card
            for card in cards
            if card["status"] in {Status.DELIVERED, Status.CANCELLED}
        ]
        settings, _ = OrderNotificationSettings.objects.get_or_create(
            tenant=request.tenant
        )
        return Response(
            {
                "columns": columns,
                "finished": finished,
                "counts": {
                    row["status"]: row["total"]
                    for row in Order.objects.filter(
                        tenant=request.tenant, abandoned_at__isnull=True
                    )
                    .filter(
                        Q(source=OrderSource.MANUAL) | Q(whatsapp_opened_at__isnull=False)
                    )
                    .values("status")
                    .annotate(total=Count("id"))
                },
                "notification_settings": _settings_json(settings),
                "server_time": value(timezone.now()),
            }
        )


class OrderOperationsDetail(MerchantAPI):
    def get(self, request, pk):
        order = _base_queryset(request.tenant).filter(pk=pk).first()
        if order is None:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        checkout = WhatsAppCheckout.objects.filter(order_id=order.pk).first()
        events = order.status_events.select_related("actor").order_by("-created_at", "-pk")[:100]
        card = _order_card(order, checkout)
        card.update(
            subtotal=str(order.subtotal),
            delivery_fee=str(order.delivery_fee),
            discount_amount=str(order.discount_amount),
            coupon_code=order.coupon_code,
            delivery_address=order.delivery_address_label,
            delivery_reference=order.delivery_reference,
            events=[
                {
                    "id": event.pk,
                    "from_status": event.from_status,
                    "from_label": STATUS_LABELS.get(event.from_status, event.from_status),
                    "to_status": event.to_status,
                    "to_label": STATUS_LABELS.get(event.to_status, event.to_status),
                    "source": event.get_source_display(),
                    "actor": (
                        event.actor.get_full_name() or event.actor.username
                        if event.actor
                        else "Sistema"
                    ),
                    "note": event.note,
                    "created_at": value(event.created_at),
                    "notification": _notification_json(getattr(event, "notification", None)),
                }
                for event in events
            ],
            items=[
                {
                    "id": item.pk,
                    "name": item.name,
                    "quantity": item.quantity,
                    "price": str(item.price),
                    "line_total": str(item.get_total_price()),
                    "notes": item.notes,
                    "combination_details": item.combination_details or {},
                }
                for item in order.items.all()
            ],
        )
        return Response(card)


class OrderTransition(MerchantAPI):
    def post(self, request, pk):
        try:
            order, event = transition_order(
                order_id=pk,
                tenant=request.tenant,
                target_status=str(request.data.get("status") or ""),
                actor=request.user,
                prep_minutes=request.data.get("prep_minutes"),
                note=str(request.data.get("note") or ""),
            )
        except Order.DoesNotExist:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        except OrderOperationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {
                "detail": "Status atualizado." if event else "O pedido já estava neste status.",
                "order": _order_card(order),
            }
        )


class OrderEstimate(MerchantAPI):
    def post(self, request, pk):
        try:
            order, _event = update_estimate(
                order_id=pk,
                tenant=request.tenant,
                minutes=request.data.get("minutes"),
                actor=request.user,
            )
        except Order.DoesNotExist:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        except OrderOperationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Previsão atualizada.", "order": _order_card(order)})


def _settings_json(settings):
    return {
        "enabled": settings.enabled,
        "notify_confirmed": settings.notify_confirmed,
        "notify_preparing": settings.notify_preparing,
        "notify_ready": settings.notify_ready,
        "notify_out_for_delivery": settings.notify_out_for_delivery,
        "notify_delivered": settings.notify_delivered,
        "notify_cancelled": settings.notify_cancelled,
        "default_prep_minutes": settings.default_prep_minutes,
    }


class OrderSettings(MerchantAPI):
    def get(self, request):
        settings, _ = OrderNotificationSettings.objects.get_or_create(
            tenant=request.tenant
        )
        return Response(_settings_json(settings))

    def post(self, request):
        settings, _ = OrderNotificationSettings.objects.get_or_create(
            tenant=request.tenant
        )
        boolean_fields = [
            "enabled",
            "notify_confirmed",
            "notify_preparing",
            "notify_ready",
            "notify_out_for_delivery",
            "notify_delivered",
            "notify_cancelled",
        ]
        for field in boolean_fields:
            if field in request.data:
                raw = request.data.get(field)
                if not isinstance(raw, bool):
                    return Response({"detail": f"Valor inválido para {field}."}, status=400)
                setattr(settings, field, raw)
        if "default_prep_minutes" in request.data:
            try:
                minutes = int(request.data.get("default_prep_minutes"))
            except (TypeError, ValueError):
                return Response({"detail": "Tempo padrão inválido."}, status=400)
            if not 5 <= minutes <= 240:
                return Response(
                    {"detail": "O tempo padrão deve ficar entre 5 e 240 minutos."},
                    status=400,
                )
            settings.default_prep_minutes = minutes
        settings.save()
        return Response({"detail": "Preferências salvas.", **_settings_json(settings)})


class ManualOrderCatalog(MerchantAPI):
    def get(self, request):
        return Response(manual_catalog(request.tenant))


class ManualOrderQuote(MerchantAPI):
    def post(self, request):
        try:
            result = quote_manual_order(
                tenant=request.tenant,
                items=request.data.get("items"),
                delivery_type=request.data.get("delivery_type") or "pickup",
                city=request.data.get("delivery_city") or "",
                neighborhood=request.data.get("delivery_neighborhood") or "",
            )
        except OrderOperationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {
                "subtotal": str(result["subtotal"]),
                "delivery_fee": str(result["delivery_fee"]),
                "total": str(result["total"]),
                "items": [
                    {
                        "name": quote.name,
                        "quantity": count,
                        "unit_price": str(quote.price),
                        "line_total": str(quote.price * count),
                    }
                    for quote, count in result["lines"]
                ],
            }
        )


class ManualOrderCreate(MerchantAPI):
    def post(self, request):
        try:
            order = create_manual_order(
                tenant=request.tenant,
                data=request.data,
                actor=request.user,
            )
        except OrderOperationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {
                "detail": f"Pedido #{order.pk} criado.",
                "id": order.pk,
            },
            status=201,
        )


def _notification_json(notice):
    if notice is None:
        return None
    if notice.sent_at:
        status = "sent"
    elif notice.skipped_at:
        status = "skipped"
    elif notice.attempted_at:
        status = "pending_retry"
    else:
        status = "pending"
    return {
        "status": status,
        "attempts": notice.attempts,
        "sent_at": value(notice.sent_at),
        "last_error": notice.last_error,
    }
