"""Authoritative cart pricing and cart-level serialization (Package 10)."""

import hashlib
import json
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps

from django.db import connection, transaction
from django.http import JsonResponse
from django.utils import timezone

from apps.stores.models import CustomizationGroup, HalfProduct, Product
from apps.tenants.models import Tenant
from .models import Cart, CartItem, CombinationPricingRule, Order

MAX_QUANTITY = 99
MAX_MONEY = Decimal("99999999.99")
DRAFT_TTL = timedelta(minutes=30)


class CartError(ValueError):
    pass


def cart_errors(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        # Session creation must survive a rejected first cart request. Otherwise
        # rollback removes its DB row and SessionMiddleware raises SessionInterrupted.
        if not request.user.is_authenticated and not request.session.session_key:
            request.session.create()
        try:
            return view(request, *args, **kwargs)
        except CartError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)

    return wrapped


def payload(request):
    try:
        data = (
            json.loads(request.body.decode("utf-8") or "{}")
            if request.content_type == "application/json"
            else request.POST.dict()
        )
    except (ValueError, UnicodeError):
        raise CartError("Dados inválidos. Atualize a página e tente novamente.")
    if not isinstance(data, dict):
        raise CartError("Os dados do pedido devem ser um objeto.")
    return data


def positive_id(value):
    if (
        isinstance(value, bool)
        or not re.fullmatch(r"[0-9]{1,18}", str(value))
        or int(value) < 1
    ):
        raise CartError("Produto ou opção inválida.")
    return int(value)


def quantity(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,3}", str(value)):
        raise CartError("Informe uma quantidade inteira entre 1 e 99.")
    result = int(value)
    if not 1 <= result <= MAX_QUANTITY:
        raise CartError("Informe uma quantidade inteira entre 1 e 99.")
    return result


def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > MAX_MONEY:
            raise ValueError
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise CartError(
            "Há um preço inválido no catálogo. Entre em contato com a loja."
        )


def ensure_store(tenant):
    if (
        tenant is None
        or not Tenant.objects.filter(pk=tenant.pk, is_active=True).exists()
    ):
        raise CartError("Esta loja não está recebendo pedidos no momento.")


def get_cart(request, tenant=None):
    tenant = tenant or getattr(request, "tenant", None)
    if tenant is None:
        raise CartError("Abra uma loja para acessar o carrinho.")
    if request.user.is_authenticated:
        lookup = {"tenant": tenant, "user": request.user, "session_key": None}
    else:
        if not request.session.session_key:
            request.session.create()
        lookup = {
            "tenant": tenant,
            "user": None,
            "session_key": request.session.session_key,
        }
    cart, _ = Cart.objects.get_or_create(**lookup)
    # Every writer acquires this lock before touching items, orders or coupons.
    if connection.in_atomic_block:
        cart = Cart.objects.select_for_update().get(pk=cart.pk)
    return cart


def invalidate_draft(cart):
    Order.objects.filter(
        source_cart_id=cart.pk,
        tenant_id=cart.tenant_id,
        whatsapp_opened_at__isnull=True,
        abandoned_at__isnull=True,
    ).update(abandoned_at=timezone.now())
    cart.checkout_token = uuid.uuid4()
    cart.save(update_fields=["checkout_token", "updated_at"])


def expired(order):
    return (
        order.whatsapp_opened_at is None
        and order.created_at <= timezone.now() - DRAFT_TTL
    )


def product_price(product):
    return money(
        product.sale_price if product.sale_price is not None else product.price
    )


def available_product(tenant, product_id):
    product = (
        Product.objects.select_related("category")
        .filter(pk=positive_id(product_id), tenant=tenant)
        .first()
    )
    today = timezone.localdate().weekday()
    if (
        product is None
        or product.category.tenant_id != tenant.pk
        or not product.is_available
        or (product.available_days and today not in product.available_days)
    ):
        name = f'O produto “{product.name}”' if product else "Este produto"
        raise CartError(
            f"{name} não está disponível hoje. Remova-o ou escolha outro item."
        )
    return product


def selection(tenant, category_id, raw, applies=None):
    if raw is None:
        raw = []
    if not isinstance(raw, list) or len(raw) > 100:
        raise CartError("Lista de adicionais inválida.")
    groups = (
        CustomizationGroup.objects.filter(
            tenant=tenant, category_id=category_id, is_active=True
        )
        .select_related("label")
        .prefetch_related("options")
    )
    if applies is not None:
        groups = groups.filter(apply_to__in=applies)
    group_map = {g.pk: g for g in groups}
    chosen = Counter()
    seen = set()
    result = []
    for item in raw:
        if not isinstance(item, dict):
            raise CartError("Adicional inválido.")
        group_id, option_id = positive_id(item.get("group_id")), positive_id(
            item.get("option_id")
        )
        group = group_map.get(group_id)
        if group is None:
            raise CartError(
                "Este grupo de adicionais não pertence ao produto ou está indisponível."
            )
        option = next(
            (
                o
                for o in group.options.all()
                if o.pk == option_id and o.tenant_id == tenant.pk and o.is_available
            ),
            None,
        )
        if option is None or option_id in seen:
            raise CartError("Adicional indisponível ou repetido. Revise suas opções.")
        seen.add(option_id)
        chosen[group_id] += 1
        result.append(
            {
                "group_id": str(group.pk),
                "group_name": group.name,
                "option_id": str(option.pk),
                "option_name": option.name,
                "price": str(money(option.price)),
                "min_choices": group.min_options,
                "is_required": group.min_options > 0,
            }
        )
    for group in group_map.values():
        if (
            group.min_options > group.max_options
            or not group.min_options <= chosen[group.pk] <= group.max_options
        ):
            raise CartError(
                f'Escolha entre {group.min_options} e {group.max_options} opção(ões) em {group.name or "adicionais"}.'
            )
    return sorted(result, key=lambda x: (int(x["group_id"]), int(x["option_id"])))


@dataclass
class Quote:
    product: object
    products: list
    name: str
    price: Decimal
    details: dict
    key: str
    notes: str


def quote(tenant, data):
    ensure_store(tenant)
    if not isinstance(data, dict):
        raise CartError("Item inválido. Remova-o e adicione novamente.")
    notes = str(data.get("notes", data.get("note", "")) or "").strip()
    if len(notes) > 2000:
        raise CartError("Use até 2.000 caracteres nas observações.")
    is_half = data.get("is_half") in (True, "true", "True", "1", 1)
    if is_half:
        ids = data.get("product_ids")
        if isinstance(ids, str):
            ids = [s.strip() for s in ids.split(",")]
        if not isinstance(ids, list) or len(ids) != 2:
            raise CartError("Escolha exatamente dois produtos para meio a meio.")
        products = [available_product(tenant, i) for i in ids]
        p1, p2 = products
        if p1.pk == p2.pk or p1.category_id != p2.category_id:
            raise CartError("Escolha dois produtos distintos da mesma categoria.")
        if (
            HalfProduct.objects.filter(
                tenant=tenant, product_id__in=[p1.pk, p2.pk], is_active=True
            ).count()
            != 2
        ):
            raise CartError("Um produto não está habilitado para meio a meio.")
        if data.get("customizations"):
            raise CartError("Adicionais devem indicar a parte do produto.")
        # Matches the existing modal: both/whole apply once to the whole item;
        # half groups are checked independently for each half.
        details = {
            "product_ids": [str(p.pk) for p in products],
            "names": [p.name for p in products],
            "images": [p.get_primary_image() or "" for p in products],
            "customizations_whole": selection(
                tenant,
                p1.category_id,
                data.get("customizations_whole"),
                ["whole", "both"],
            ),
            "customizations_half1": selection(
                tenant, p1.category_id, data.get("customizations_half1"), ["half"]
            ),
            "customizations_half2": selection(
                tenant, p2.category_id, data.get("customizations_half2"), ["half"]
            ),
            "notes_half1": str(data.get("notes_half1") or "").strip(),
            "notes_half2": str(data.get("notes_half2") or "").strip(),
        }
        if any(len(details[k]) > 2000 for k in ["notes_half1", "notes_half2"]):
            raise CartError("Use até 2.000 caracteres nas observações.")
        # Commercial rule: the most expensive pizza, plus the chosen extras.
        # Historical average rules must not change the advertised price.
        prices = [product_price(p) for p in products]
        price = max(prices)
        name, product = " / ".join(p.name for p in products)[:200], None
    else:
        if any(
            data.get(k)
            for k in (
                "customizations_whole",
                "customizations_half1",
                "customizations_half2",
                "product_ids",
            )
        ):
            raise CartError("Combinação de adicionais inválida.")
        product = available_product(tenant, data.get("product_id"))
        products = [product]
        details = {
            "customizations": selection(
                tenant, product.category_id, data.get("customizations")
            )
        }
        name, price = product.name, product_price(product)
    buckets = (
        "customizations",
        "customizations_whole",
        "customizations_half1",
        "customizations_half2",
    )
    price = money(
        price
        + sum(
            (Decimal(c["price"]) for k in buckets for c in details.get(k, [])),
            Decimal("0"),
        )
    )
    # Keys describe choices, never client prices or current catalog labels.
    identity = {
        "products": [p.pk for p in products],
        "notes": notes,
        "parts": {
            k: [(c["group_id"], c["option_id"]) for c in details.get(k, [])]
            for k in buckets
        },
        "half_notes": [details.get("notes_half1", ""), details.get("notes_half2", "")],
    }
    key = (
        "v10:"
        + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    )
    return Quote(product, products, name, price, details, key, notes)


def item_payload(item):
    details = item.combination_details or {}
    if not isinstance(details, dict):
        raise CartError("Item antigo inválido. Remova-o e adicione novamente.")
    return {
        **details,
        "is_half": bool(details.get("product_ids")),
        "product_id": item.product_id,
        "notes": item.notes or "",
    }


def check_quantity(q, count):
    count = quantity(count)
    for p in q.products:
        if count < max(1, p.min_order_qty) or (
            p.max_order_qty is not None and count > p.max_order_qty
        ):
            raise CartError(
                f"A quantidade de {p.name} deve respeitar o mínimo de {max(1, p.min_order_qty)} e o máximo de {p.max_order_qty or MAX_QUANTITY}."
            )
    money(q.price * count)
    return count


def validate_totals(lines):
    totals, limits = Counter(), {}
    total = Decimal("0")
    for q, count in lines:
        check_quantity(q, count)
        total += q.price * count
        for p in q.products:
            totals[p.pk] += count
            limits[p.pk] = min(
                p.max_order_qty if p.max_order_qty is not None else MAX_QUANTITY,
                MAX_QUANTITY,
            )
    if any(totals[pk] > limits[pk] for pk in totals):
        raise CartError(
            "O carrinho ultrapassa o limite de quantidade de um produto, somando suas variações."
        )
    return money(total)


def check_cart_candidate(cart, q, count, exclude_ids=()):
    lines = [(q, count)]
    for item in cart.items.exclude(pk__in=exclude_ids).select_related("product"):
        lines.append((quote(cart.tenant, item_payload(item)), item.quantity))
    validate_totals(lines)
    from .inventory import check_stock
    check_stock(lines, exclude_cart_id=cart.pk)


def add_item(cart, q, count):
    count = quantity(count)
    item = cart.items.filter(product_key=q.key).first()
    count += item.quantity if item else 0
    check_cart_candidate(cart, q, count, [item.pk] if item else [])
    values = dict(
        product=q.product,
        name=q.name,
        price=q.price,
        quantity=count,
        combination_details=q.details,
        notes=q.notes,
    )
    if item:
        for key, value in values.items():
            setattr(item, key, value)
        item.save(update_fields=list(values))
    else:
        item = CartItem.objects.create(cart=cart, product_key=q.key, **values)
    invalidate_draft(cart)
    return item


def quote_changed(item, q):
    # Media URLs can have expiring signatures; they do not change the purchase.
    old = {k: v for k, v in (item.combination_details or {}).items() if k != "images"}
    new = {k: v for k, v in q.details.items() if k != "images"}
    return item.price != q.price or old != new or item.name != q.name


def refresh_cart(cart):
    """Validate every line first; update prices/snapshots without changing choices."""
    items = list(cart.items.select_related("product").order_by("pk"))
    quoted = [(item, quote(cart.tenant, item_payload(item))) for item in items]
    validate_totals([(q, item.quantity) for item, q in quoted])
    from .inventory import check_stock
    check_stock([(q, item.quantity) for item, q in quoted], exclude_cart_id=cart.pk)
    changes = []
    for item, q in quoted:
        if quote_changed(item, q):
            changes.append({
                "name": q.name,
                "old_price": item.price,
                "new_price": q.price,
                "quantity": item.quantity,
                "total": money(q.price * item.quantity),
            })
            item.price, item.combination_details, item.name = q.price, q.details, q.name
            item.save(update_fields=["price", "combination_details", "name"])
    if changes:
        invalidate_draft(cart)
    return items, changes
