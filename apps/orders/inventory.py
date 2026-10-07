"""Stock reservations and movements, serialized by sorted product row locks.

Callers lock cart/order before this module; coupon locks (when any) precede
product locks. No operation here locks another cart, order or coupon.
"""
from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.stores.models import Product
from .models import Cart, Order, StockReservation


def requirements(lines):
    demand = Counter()
    for quote, count in lines:
        share = Decimal(count) / len(quote.products)
        for product in quote.products:
            demand[product.pk] += share
    return demand


def active_reservations():
    from .cart_service import DRAFT_TTL
    return StockReservation.objects.filter(
        deducted_quantity=0,
        order__abandoned_at__isnull=True,
        order__whatsapp_opened_at__isnull=True,
        order__created_at__gt=timezone.now() - DRAFT_TTL,
    ).exclude(order__status='cancelled')


def check_stock(lines, *, exclude_cart_id=None, exclude_order_id=None, exclude_whatsapp_checkout_id=None, lock=False):
    from .cart_service import CartError
    demand = requirements(lines)
    qs = Product.objects.filter(pk__in=demand).order_by('pk')
    if lock:
        qs = qs.select_for_update()
    products = {p.pk: p for p in qs}
    if len(products) != len(demand):
        raise CartError('Um produto foi removido. Confira o carrinho novamente.')
    reservations = active_reservations().filter(product_id__in=demand)
    if exclude_cart_id is not None:
        reservations = reservations.exclude(order__source_cart_id=exclude_cart_id)
    if exclude_order_id is not None:
        reservations = reservations.exclude(order_id=exclude_order_id)
    reserved = dict(reservations.values('product_id').annotate(amount=Sum('quantity')).values_list('product_id', 'amount'))
    from apps.integrations.models import WhatsAppCartReservation
    wa_reservations = WhatsAppCartReservation.objects.filter(product_id__in=demand)
    if exclude_whatsapp_checkout_id is not None:
        wa_reservations = wa_reservations.exclude(checkout_id=exclude_whatsapp_checkout_id)
    for pk, amount in wa_reservations.values('product_id').annotate(amount=Sum('quantity')).values_list('product_id', 'amount'):
        reserved[pk] = reserved.get(pk, Decimal('0')) + amount
    for pk, amount in demand.items():
        p = products[pk]
        if p.stock is not None:
            available = max(Decimal('0'), p.stock - reserved.get(pk, Decimal('0')))
            if amount > available:
                display = format(available, '.2f').replace('.', ',')
                raise CartError(f'Estoque insuficiente de “{p.name}”. Disponível: {display} unidade(s). Reduza a quantidade ou remova o item.')
    return products, demand


@transaction.atomic
def reserve(order, lines):
    products, demand = check_stock(lines, exclude_order_id=order.pk, lock=True)
    for pk, amount in demand.items():
        StockReservation.objects.update_or_create(
            order=order, product=products[pk],
            defaults={'product_name': products[pk].name, 'quantity': amount},
        )


@transaction.atomic
def consume(order, lines, *, exclude_whatsapp_checkout_id=None):
    """Only called with a locked order that has not been sent or cancelled."""
    from .cart_service import CartError
    if order.whatsapp_opened_at or order.status == 'cancelled':
        raise CartError('Este pedido já foi encaminhado ou cancelado.')
    products, demand = check_stock(lines, exclude_order_id=order.pk, exclude_whatsapp_checkout_id=exclude_whatsapp_checkout_id, lock=True)
    for pk, amount in demand.items():
        p = products[pk]
        movement, _ = StockReservation.objects.get_or_create(
            order=order, product=p, defaults={'product_name': p.name, 'quantity': amount},
        )
        if movement.deducted_quantity:
            raise CartError('O estoque deste pedido já foi processado.')
        if p.stock is not None:
            Product.objects.filter(pk=pk).update(stock=F('stock') - amount)
            movement.deducted_quantity = amount
            movement.save(update_fields=['deducted_quantity'])


def _cancel_locked(order_id, tenant, *, allowed_statuses=None):
    """Cancel with the historical cart -> order -> products lock ordering.

    Returns ``(changed, previous_status, order)`` so the operational state
    machine can append its audit event without reordering locks. Legacy callers
    keep using ``cancel`` below and still receive a boolean.
    """
    from .cart_service import CartError, invalidate_draft

    candidate = Order.objects.get(pk=order_id, tenant=tenant)
    cart = Cart.objects.select_for_update().filter(
        pk=candidate.source_cart_id, tenant=tenant
    ).first()
    order = Order.objects.select_for_update().get(pk=order_id, tenant=tenant)
    if order.status == 'cancelled':
        return False, 'cancelled', order
    if allowed_statuses is not None and order.status not in set(allowed_statuses):
        raise CartError('Este pedido não pode mais ser cancelado por este fluxo.')

    previous_status = order.status
    movements = list(
        order.stock_reservations.filter(returned_at__isnull=True).order_by('product_id')
    )
    products = {
        p.pk: p
        for p in Product.objects.select_for_update()
        .filter(
            pk__in=[m.product_id for m in movements if m.product_id],
            tenant=tenant,
        )
        .order_by('pk')
    }
    now = timezone.now()
    for movement in movements:
        p = products.get(movement.product_id)
        if p is not None and p.stock is not None and movement.deducted_quantity:
            Product.objects.filter(pk=p.pk).update(
                stock=F('stock') + movement.deducted_quantity
            )
        movement.returned_at = now
        movement.save(update_fields=['returned_at'])
    order.status = 'cancelled'
    if hasattr(order, 'status_updated_at'):
        order.status_updated_at = now
        order.save(update_fields=['status', 'status_updated_at'])
    else:  # migration compatibility for historical migration/test states
        order.save(update_fields=['status'])
    if (
        order.whatsapp_opened_at is None
        and cart
        and str(cart.checkout_token) == str(order.checkout_token)
    ):
        invalidate_draft(cart)
    return True, previous_status, order


@transaction.atomic
def cancel_with_previous(order_id, tenant, *, allowed_statuses=None):
    return _cancel_locked(order_id, tenant, allowed_statuses=allowed_statuses)


@transaction.atomic
def cancel(order_id, tenant):
    """Cancel through the tenant panel; cart -> order -> products lock order."""
    changed, _previous, _order = _cancel_locked(order_id, tenant)
    return changed
