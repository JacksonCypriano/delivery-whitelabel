import urllib.parse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.tenants.delivery import resolve_delivery
from apps.marketplace.services import build_tenant_url

from .models import (
    Cart,
    Order,
)
from .services import build_whatsapp_message
from . import cart_service as integrity
from apps.coupons.models import CouponCampaign
from apps.coupons.services import validate_coupon


def _customer_for_request(request):
    if not request.user.is_authenticated:
        return None

    return Customer.objects.filter(user=request.user).first()


def _cart_for_tenant(request, tenant):
    return integrity.get_cart(request, tenant)


def _owned_order(request, public_token):
    candidate = get_object_or_404(
        Order,
        tenant=request.tenant,
        public_token=public_token,
        abandoned_at__isnull=True,
    )
    carts = Cart.objects.filter(pk=candidate.source_cart_id, tenant=request.tenant)
    if request.user.is_authenticated:
        carts = carts.filter(user=request.user)
    else:
        carts = carts.filter(user__isnull=True, session_key=request.session.session_key)
    cart = carts.select_for_update().first()
    customer = _customer_for_request(request)
    if cart is None and (customer is None or candidate.customer_id != customer.pk):
        raise Http404
    order = get_object_or_404(
        Order.objects.select_for_update(), pk=candidate.pk, abandoned_at__isnull=True
    )
    return order, cart


@transaction.atomic
def open_whatsapp(request, public_token):
    order, cart = _owned_order(request, public_token)
    if order.whatsapp_opened_at is None:
        try:
            integrity.ensure_store(request.tenant)
            if order.status == "cancelled":
                raise integrity.CartError("Este pedido foi cancelado.")
            if cart is None or integrity.expired(order):
                raise integrity.CartError(
                    "A revisão do pedido expirou. Confira os valores e confirme novamente."
                )
            items = list(order.items.select_related("product"))
            if not items:
                raise integrity.CartError("O pedido está vazio.")
            quoted = [
                (item, integrity.quote(request.tenant, integrity.item_payload(item)))
                for item in items
            ]
            subtotal = integrity.validate_totals(
                [(q, item.quantity) for item, q in quoted]
            )
            if subtotal != order.subtotal or any(
                integrity.quote_changed(item, q) for item, q in quoted
            ):
                raise integrity.CartError(
                    "Os preços ou opções mudaram. Confira o checkout novamente."
                )
            delivery = resolve_delivery(
                tenant=request.tenant,
                delivery_type=order.delivery_type,
                city=order.delivery_city,
                neighborhood=order.delivery_neighborhood,
            )
            if not delivery["available"] or delivery["fee"] != order.delivery_fee:
                raise integrity.CartError(
                    "A entrega ou a taxa mudou. Confira o checkout novamente."
                )
            if order.coupon_code:
                campaign = (
                    CouponCampaign.objects.select_for_update()
                    .filter(tenant=request.tenant, code=order.coupon_code)
                    .first()
                )
                if campaign is None:
                    raise integrity.CartError("O cupom não está mais disponível.")
                result = validate_coupon(
                    code=campaign.code,
                    tenant=request.tenant,
                    customer=order.customer,
                    subtotal=order.subtotal,
                    delivery_fee=order.delivery_fee,
                    exclude_order_id=order.pk,
                )
                if not result["valid"]:
                    raise integrity.CartError(result["message"])
                if (
                    result["discount"] != order.discount_amount
                    or result["final_total"] != order.total
                ):
                    raise integrity.CartError(
                        "O desconto mudou. Confira o checkout novamente."
                    )
        except integrity.CartError as exc:
            order.abandoned_at = timezone.now()
            order.save(update_fields=["abandoned_at"])
            if cart:
                integrity.invalidate_draft(cart)
            messages.error(request, str(exc))
            return redirect("checkout:checkout_step_one")
        order.whatsapp_opened_at = timezone.now()
        order.save(update_fields=["whatsapp_opened_at"])
        cart.items.all().delete()
        integrity.invalidate_draft(cart)
        request.session["checkout_token"] = str(cart.checkout_token)
    # Reopening an old order must never delete the customer's new cart.
    message = build_whatsapp_message(order)
    return redirect(
        f'https://wa.me/{order.tenant.whatsapp_number}?text={urllib.parse.quote(message, safe="")}'
    )


@require_POST
@transaction.atomic
def edit_generated_order(request, public_token):
    order, cart = _owned_order(request, public_token)
    if order.whatsapp_opened_at is None:
        order.abandoned_at = timezone.now()
        order.save(update_fields=["abandoned_at"])
        if cart:
            integrity.invalidate_draft(cart)
            request.session["checkout_token"] = str(cart.checkout_token)
    else:
        messages.info(
            request,
            "Este pedido já foi encaminhado. Para fazer outro, use Repetir pedido.",
        )
    return redirect("checkout:cart")


@login_required
def order_history(request):
    customer = _customer_for_request(request)

    orders = Order.objects.none()

    if customer:
        orders = (
            Order.objects.filter(customer=customer, abandoned_at__isnull=True)
            .select_related("tenant", "tenant__brand_config")
            .prefetch_related("items")
            .order_by("-created_at")
        )

    paginator = Paginator(orders, 8)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request, "orders/history.html", {"orders": page_obj, "page_obj": page_obj}
    )


@login_required
@require_POST
@transaction.atomic
def repeat_order(request, public_token):
    customer = _customer_for_request(request)

    if customer is None:
        messages.error(
            request,
            "Não foi possível localizar seu cadastro.",
        )
        return redirect("orders:history")

    order = get_object_or_404(
        Order.objects.select_related("tenant").prefetch_related("items__product"),
        public_token=public_token,
        customer=customer,
        abandoned_at__isnull=True,
    )

    cart = _cart_for_tenant(
        request,
        order.tenant,
    )

    added = 0
    skipped = 0
    for old_item in order.items.all():
        try:
            # Savepoint avoids leaving partial line changes if validation fails.
            with transaction.atomic():
                q = integrity.quote(order.tenant, integrity.item_payload(old_item))
                integrity.add_item(cart, q, old_item.quantity)
        except integrity.CartError:
            skipped += 1
            continue
        added += 1

    if added:
        messages.success(
            request,
            (
                "Pedido adicionado ao carrinho. "
                "Os preços dos produtos foram "
                "recalculados com os valores atuais."
            ),
        )

    if skipped:
        messages.warning(
            request,
            (
                f"{skipped} item(ns) não foram "
                "adicionados porque não estão mais "
                "disponíveis."
            ),
        )

    cart_url = build_tenant_url(order.tenant).rstrip("/") + "/carrinho/"

    return redirect(cart_url)
