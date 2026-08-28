import hashlib
import json
import urllib.parse
import uuid
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.marketplace.services import build_tenant_url
from apps.stores.models import Product

from .models import (
    Cart,
    CartItem,
    CombinationPricingRule,
    Order,
)
from .services import build_whatsapp_message


def _rotate_checkout_token(request):
    token = str(uuid.uuid4())
    request.session["checkout_token"] = token
    request.session.modified = True
    return token


def _customer_for_request(request):
    if not request.user.is_authenticated:
        return None

    return (
        Customer.objects
        .filter(user=request.user)
        .first()
    )


def _cart_for_tenant(request, tenant):
    cart = (
        Cart.objects
        .filter(
            tenant=tenant,
            user=request.user,
        )
        .order_by("-updated_at")
        .first()
    )

    if cart is not None:
        return cart

    return Cart.objects.create(
        tenant=tenant,
        user=request.user,
        session_key=None,
    )


def _to_decimal(value):
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0.00")


def _sum_customizations(items):
    total = Decimal("0.00")

    for item in items or []:
        if not isinstance(item, dict):
            continue

        total += _to_decimal(
            item.get("price", 0)
        )

    return total


def _repeat_unit_price(order_item):
    combo = order_item.combination_details or {}
    tenant = order_item.order.tenant

    product_ids = combo.get("product_ids") or []

    if product_ids:
        products = list(
            Product.objects
            .filter(
                tenant=tenant,
                id__in=product_ids,
                is_available=True,
            )
        )

        if len(products) != 2:
            return None

        by_id = {
            str(product.id): product
            for product in products
        }

        if any(
            str(product_id) not in by_id
            for product_id in product_ids
        ):
            return None

        prices = [
            _to_decimal(
                product.sale_price
                if product.sale_price
                else product.price
            )
            for product in (
                by_id[str(product_ids[0])],
                by_id[str(product_ids[1])],
            )
        ]

        try:
            rule = CombinationPricingRule.objects.get(
                tenant=tenant,
                combination_type="half_half",
            )
            method = rule.price_calculation_method
        except CombinationPricingRule.DoesNotExist:
            method = "max_price"

        if method == "max_price":
            base = max(prices)
        else:
            base = sum(prices) / Decimal("2")

        additions = (
            _sum_customizations(
                combo.get("customizations_whole")
            )
            + _sum_customizations(
                combo.get("customizations_half1")
            )
            + _sum_customizations(
                combo.get("customizations_half2")
            )
        )

        return base + additions

    product = order_item.product

    if (
        product is None
        or not product.is_available
        or product.tenant_id != tenant.id
    ):
        return None

    base = _to_decimal(
        product.sale_price
        if product.sale_price
        else product.price
    )

    return (
        base
        + _sum_customizations(
            combo.get("customizations")
        )
    )


def _repeat_product_key(order_item):
    if order_item.product_key:
        return order_item.product_key

    payload = {
        "name": order_item.name,
        "combination_details": (
            order_item.combination_details
            or {}
        ),
        "notes": order_item.notes or "",
    }

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    )

    return (
        "repeat:"
        + hashlib.sha1(
            raw.encode("utf-8")
        ).hexdigest()[:32]
    )


def open_whatsapp(request, public_token):
    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        tenant=request.tenant,
        public_token=public_token,
        abandoned_at__isnull=True,
    )

    if order.whatsapp_opened_at is None:
        order.whatsapp_opened_at = timezone.now()
        order.save(
            update_fields=["whatsapp_opened_at"]
        )

    if (
        order.source_cart_id
        and getattr(request, "tenant", None)
    ):
        cart_filter = {
            "id": order.source_cart_id,
            "tenant": request.tenant,
        }

        if request.user.is_authenticated:
            cart_filter["user"] = request.user
        else:
            cart_filter["session_key"] = (
                request.session.session_key
            )

        Cart.objects.filter(
            **cart_filter
        ).delete()

    _rotate_checkout_token(request)

    message = build_whatsapp_message(order)

    whatsapp_url = (
        f"https://wa.me/"
        f"{order.tenant.whatsapp_number}"
        f"?text="
        f"{urllib.parse.quote(message, safe='')}"
    )

    return redirect(whatsapp_url)


@require_POST
def edit_generated_order(request, public_token):
    order = get_object_or_404(
        Order,
        tenant=request.tenant,
        public_token=public_token,
        abandoned_at__isnull=True,
    )

    if order.whatsapp_opened_at is None:
        order.abandoned_at = timezone.now()
        order.save(
            update_fields=["abandoned_at"]
        )

    _rotate_checkout_token(request)

    return redirect("checkout:cart")


@login_required
def order_history(request):
    customer = _customer_for_request(request)

    orders = Order.objects.none()

    if customer:
        orders = (
            Order.objects
            .filter(customer=customer, abandoned_at__isnull=True)
            .select_related("tenant", "tenant__brand_config")
            .prefetch_related("items")
            .order_by("-created_at")
        )

    paginator = Paginator(orders, 8)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "orders/history.html", {"orders": page_obj, "page_obj": page_obj})


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
        Order.objects
        .select_related("tenant")
        .prefetch_related("items__product"),
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
        unit_price = _repeat_unit_price(
            old_item
        )

        if unit_price is None:
            skipped += 1
            continue

        key = _repeat_product_key(
            old_item
        )

        defaults = {
            "product": old_item.product,
            "name": old_item.name,
            "price": unit_price,
            "quantity": old_item.quantity,
            "combination_details": (
                old_item.combination_details
                or {}
            ),
            "notes": old_item.notes or "",
        }

        item, created = (
            CartItem.objects
            .get_or_create(
                cart=cart,
                product_key=key,
                defaults=defaults,
            )
        )

        if not created:
            item.quantity += old_item.quantity
            item.price = unit_price
            item.combination_details = (
                old_item.combination_details
                or {}
            )
            item.notes = old_item.notes or ""
            item.product = old_item.product
            item.name = old_item.name
            item.save(
                update_fields=[
                    "quantity",
                    "price",
                    "combination_details",
                    "notes",
                    "product",
                    "name",
                ]
            )

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

    cart_url = (
        build_tenant_url(order.tenant)
        .rstrip("/")
        + "/carrinho/"
    )

    return redirect(cart_url)
