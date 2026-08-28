# apps/checkout/views.py
import hashlib
import json
import logging
import urllib.parse
import uuid
from decimal import Decimal, InvalidOperation

from django.apps import apps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.customers.models import Customer, CustomerAddress
from apps.marketplace.location import (
    get_global_delivery_location,
    serialize_customer_address,
    serialize_manual_address,
    set_global_delivery_location,
)
from apps.coupons.models import CouponCampaign, CouponRedemption
from apps.coupons.services import validate_coupon
from apps.orders.models import Cart, CartItem, CombinationPricingRule, Order, OrderItem
from apps.stores.models import Product
from apps.tenants.delivery import delivery_result_to_json, resolve_delivery
from apps.tenants.models import DeliveryZone

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_decimal(value, default='0.00'):
    try:
        if value is None or value == '':
            return Decimal(default)
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)



def get_cart_delivery_summary(request, subtotal=None):
    """
    Calcula o resumo comercial do carrinho usando o endereço global.

    Regras:
    - loja somente retirada: frete 0 e checkout permitido;
    - endereço global atendido: usa a taxa real do DeliveryZone;
    - endereço ausente/não atendido:
        * se aceita retirada, checkout continua permitido para retirada;
        * se é delivery-only, checkout fica bloqueado até trocar endereço.
    """
    tenant = request.tenant
    location = get_global_delivery_location(request)

    if subtotal is None:
        subtotal = Decimal("0.00")

    subtotal = to_decimal(subtotal)

    accepts_delivery = bool(
        getattr(tenant, "accepts_delivery", False)
    )
    accepts_pickup = bool(
        getattr(tenant, "accepts_pickup", False)
    )

    if not accepts_delivery:
        delivery_result = {
            "available": False,
            "found": False,
            "fee": Decimal("0.00"),
            "fee_display": "Retirada",
            "message": "Esta loja trabalha somente com retirada.",
            "source": "pickup_only",
        }

        return {
            "location": location,
            "delivery_result": delivery_result,
            "delivery_available": False,
            "delivery_fee": Decimal("0.00"),
            "delivery_fee_display": "Retirada",
            "total": subtotal,
            "can_checkout": accepts_pickup,
            "checkout_mode_hint": "pickup",
            "status": "pickup_only",
        }

    if not location:
        return {
            "location": None,
            "delivery_result": None,
            "delivery_available": None,
            "delivery_fee": Decimal("0.00"),
            "delivery_fee_display": "A calcular",
            "total": subtotal,
            "can_checkout": accepts_pickup,
            "checkout_mode_hint": (
                "pickup"
                if accepts_pickup
                else "address_required"
            ),
            "status": "address_required",
        }

    delivery_result = resolve_delivery(
        tenant=tenant,
        delivery_type="delivery",
        city=location.get("city", ""),
        neighborhood=location.get("neighborhood", ""),
    )

    if delivery_result["available"]:
        delivery_fee = to_decimal(
            delivery_result.get("fee", Decimal("0.00"))
        )

        return {
            "location": location,
            "delivery_result": delivery_result,
            "delivery_available": True,
            "delivery_fee": delivery_fee,
            "delivery_fee_display": delivery_result[
                "fee_display"
            ],
            "total": subtotal + delivery_fee,
            "can_checkout": True,
            "checkout_mode_hint": "delivery",
            "status": "delivery_available",
        }

    return {
        "location": location,
        "delivery_result": delivery_result,
        "delivery_available": False,
        "delivery_fee": Decimal("0.00"),
        "delivery_fee_display": "Indisponível",
        "total": subtotal,
        "can_checkout": accepts_pickup,
        "checkout_mode_hint": (
            "pickup"
            if accepts_pickup
            else "address_unavailable"
        ),
        "status": "delivery_unavailable",
    }


def cart_summary_json(request, subtotal, total_items):
    summary = get_cart_delivery_summary(
        request,
        subtotal=subtotal,
    )

    return {
        "subtotal": str(
            to_decimal(subtotal).quantize(Decimal("0.01"))
        ),
        "subtotal_display": (
            f"R$ {to_decimal(subtotal):.2f}"
            .replace(".", ",")
        ),
        "delivery_fee": str(
            summary["delivery_fee"].quantize(
                Decimal("0.01")
            )
        ),
        "delivery_fee_display": (
            summary["delivery_fee_display"]
        ),
        "total": str(
            summary["total"].quantize(Decimal("0.01"))
        ),
        "total_display": (
            f"R$ {summary['total']:.2f}"
            .replace(".", ",")
        ),
        "delivery_available": (
            summary["delivery_available"]
        ),
        "delivery_status": summary["status"],
        "can_checkout": summary["can_checkout"],
        "checkout_mode_hint": (
            summary["checkout_mode_hint"]
        ),
        "cart_count": int(total_items),
    }


def get_cart_item_price_breakdown(item):
    """
    Decompõe o preço unitário salvo no CartItem.

    CartItem.price já é o valor final unitário:
        preço base + adicionais

    Para preservar o snapshot do carrinho, NÃO buscamos novamente
    o preço atual do Product. Em vez disso:

        adicionais = soma dos adicionais salvos em combination_details
        preço base = item.price - adicionais

    Isso funciona tanto para produto simples quanto para meio a meio.
    """
    combo = item.combination_details or {}

    customizations = []

    if combo.get("product_ids"):
        customizations.extend(
            combo.get("customizations_whole") or []
        )
        customizations.extend(
            combo.get("customizations_half1") or []
        )
        customizations.extend(
            combo.get("customizations_half2") or []
        )
    else:
        customizations.extend(
            combo.get("customizations") or []
        )

    additions_unit_price = sum_customizations_price(
        customizations
    )

    final_unit_price = to_decimal(
        item.price
    )

    base_unit_price = (
        final_unit_price
        - additions_unit_price
    )

    # Proteção contra dados antigos/inconsistentes.
    if base_unit_price < Decimal("0.00"):
        base_unit_price = final_unit_price
        additions_unit_price = Decimal("0.00")

    quantity = max(
        int(getattr(item, "quantity", 0) or 0),
        0,
    )

    return {
        "base_unit_price": base_unit_price,
        "additions_unit_price": additions_unit_price,
        "final_unit_price": final_unit_price,
        "base_total": (
            base_unit_price * quantity
        ),
        "additions_total": (
            additions_unit_price * quantity
        ),
        "line_total": (
            final_unit_price * quantity
        ),
        "has_additions": (
            additions_unit_price
            > Decimal("0.00")
        ),
    }


def populate_cart_item_price_breakdown(items):
    """
    Adiciona atributos calculados aos objetos CartItem apenas
    para renderização. Não persiste nada no banco.
    """
    for item in items:
        breakdown = get_cart_item_price_breakdown(
            item
        )

        item.base_unit_price = breakdown[
            "base_unit_price"
        ]

        item.additions_unit_price = breakdown[
            "additions_unit_price"
        ]

        item.final_unit_price = breakdown[
            "final_unit_price"
        ]

        item.base_total = breakdown[
            "base_total"
        ]

        item.additions_total = breakdown[
            "additions_total"
        ]

        item.line_total = breakdown[
            "line_total"
        ]

        item.has_additions = breakdown[
            "has_additions"
        ]


CUSTOMIZATION_BUCKETS = {
    'customizations',
    'customizations_whole',
    'customizations_half1',
    'customizations_half2',
}


def get_customization_min_choices(customization):
    if not isinstance(customization, dict):
        return 0

    minimum = _to_non_negative_int(
        customization.get('min_choices', customization.get('min_selection', customization.get('minimum_choices', 0))),
        default=0,
    )
    required = _to_bool(customization.get('is_required', customization.get('required', False)))

    group_id = str(customization.get('group_id', '') or '').strip()

    if group_id:
        try:
            group_model = apps.get_model('stores', 'CustomizationGroup')
            group = group_model.objects.filter(pk=group_id).first()

            if group:
                for field_name in ('min_choices', 'min_selection', 'minimum_choices', 'minimum'):
                    if hasattr(group, field_name):
                        minimum = max(minimum, _to_non_negative_int(getattr(group, field_name), default=0))
                        break

                for field_name in ('is_required', 'required', 'mandatory'):
                    if hasattr(group, field_name):
                        required = required or _to_bool(getattr(group, field_name))
                        break
        except (LookupError, ValueError, TypeError):
            pass

    if required and minimum == 0:
        minimum = 1

    return minimum


def customization_can_be_removed(customizations, index):
    if not isinstance(customizations, list) or index < 0 or index >= len(customizations):
        return False

    customization = customizations[index]

    if not isinstance(customization, dict):
        return False

    minimum = get_customization_min_choices(customization)

    if minimum <= 0:
        return True

    group_id = str(customization.get('group_id', '') or '')
    group_name = str(customization.get('group_name', '') or '')

    if group_id:
        selected_in_group = sum(
            1 for current in customizations
            if isinstance(current, dict) and str(current.get('group_id', '') or '') == group_id
        )
    else:
        selected_in_group = sum(
            1 for current in customizations
            if isinstance(current, dict) and str(current.get('group_name', '') or '') == group_name
        )

    return (selected_in_group - 1) >= minimum


def populate_customization_removal_flags(items):
    for item in items:
        combo = item.combination_details or {}

        for bucket in CUSTOMIZATION_BUCKETS:
            customizations = combo.get(bucket) or []

            if not isinstance(customizations, list):
                continue

            for index, customization in enumerate(customizations):
                if isinstance(customization, dict):
                    customization['can_remove_from_cart'] = customization_can_be_removed(customizations, index)


def get_all_customizations_from_combo(combo):
    if not isinstance(combo, dict):
        return []

    if combo.get('product_ids'):
        return (
            list(combo.get('customizations_whole') or [])
            + list(combo.get('customizations_half1') or [])
            + list(combo.get('customizations_half2') or [])
        )

    return list(combo.get('customizations') or [])


def rebuild_cart_item_key(item, combo):
    if combo.get('product_ids'):
        product_ids = [str(value) for value in (combo.get('product_ids') or [])]

        if len(product_ids) == 2:
            ids_sorted = sorted(product_ids, key=lambda value: (0, int(value)) if value.isdigit() else (1, value))
            payload = {
                'type': 'half_half',
                'product_ids': ids_sorted,
                'customizations_whole': combo.get('customizations_whole') or [],
                'customizations_half1': combo.get('customizations_half1') or [],
                'customizations_half2': combo.get('customizations_half2') or [],
                'notes_half1': combo.get('notes_half1', ''),
                'notes_half2': combo.get('notes_half2', ''),
                'notes': item.notes or '',
            }
            return build_cart_item_key(f'half:{ids_sorted[0]}:{ids_sorted[1]}', payload)

    payload = {
        'type': 'single_product',
        'product_id': str(item.product_id or ''),
        'customizations': combo.get('customizations') or [],
        'notes': item.notes or '',
    }
    return build_cart_item_key(f'product:{item.product_id or "snapshot"}', payload)


def cart_item_prices_json(item):
    breakdown = get_cart_item_price_breakdown(item)

    def money(value):
        return f'R$ {to_decimal(value):.2f}'.replace('.', ',')

    return {
        'item_id': item.id,
        'quantity': int(item.quantity),
        'base_unit_price': str(breakdown['base_unit_price'].quantize(Decimal('0.01'))),
        'base_unit_price_display': money(breakdown['base_unit_price']),
        'additions_unit_price': str(breakdown['additions_unit_price'].quantize(Decimal('0.01'))),
        'additions_unit_price_display': money(breakdown['additions_unit_price']),
        'final_unit_price': str(breakdown['final_unit_price'].quantize(Decimal('0.01'))),
        'final_unit_price_display': money(breakdown['final_unit_price']),
        'line_total': str(breakdown['line_total'].quantize(Decimal('0.01'))),
        'line_total_display': money(breakdown['line_total']),
        'has_additions': bool(breakdown['has_additions']),
    }


def get_notes_from_payload(data):
    return (data.get('notes') or data.get('note') or '').strip()


def _to_non_negative_int(value, default=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on', 'sim'}


def normalize_customization_list(raw_list):
    if not isinstance(raw_list, (list, tuple)):
        return []

    normalized = []

    for item in raw_list:
        if not isinstance(item, dict):
            continue

        price = to_decimal(item.get('price', 0))
        is_required = _to_bool(item.get('is_required', item.get('required', False)))
        min_choices = _to_non_negative_int(
            item.get('min_choices', item.get('min_selection', item.get('minimum_choices', 0))),
            default=0,
        )

        if is_required and min_choices == 0:
            min_choices = 1

        normalized.append({
            'group_id': str(item.get('group_id', '') or ''),
            'group_name': str(item.get('group_name', '') or ''),
            'option_id': str(item.get('option_id', '') or ''),
            'option_name': str(item.get('option_name', '') or ''),
            'price': str(price),
            'min_choices': min_choices,
            'is_required': is_required,
        })

    return normalized


def sum_customizations_price(customizations):
    total = Decimal('0.00')
    for item in customizations:
        if not isinstance(item, dict):
            continue
        total += to_decimal(item.get('price', 0))
    return total


def build_cart_item_key(prefix, payload):
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]
    return f'{prefix}:{digest}'


def get_image_url_from_product(product):
    if not product:
        return ''
    try:
        getter = getattr(product, 'get_primary_image', None)
        val = getter() if callable(getter) else getter
        if isinstance(val, str) and val:
            return val
        if hasattr(val, 'url'):
            return val.url
    except Exception:
        pass
    for attr in ('image', 'primary_image', 'thumbnail'):
        try:
            val = getattr(product, attr, None)
            if not val:
                continue
            if isinstance(val, str) and val:
                return val
            if hasattr(val, 'url'):
                return val.url
        except Exception:
            continue
    return ''


def populate_combination_images_for_items(items, tenant=None, persist=False):
    for item in items:
        combo = getattr(item, 'combination_details', None)
        if not combo or not isinstance(combo, dict):
            continue
        images = combo.get('images') or []
        if images and any(str(i).strip() for i in images):
            continue
        new_images = []
        ids = combo.get('product_ids') or []
        names = combo.get('names') or []
        if ids:
            for pid in ids:
                try:
                    prod = Product.objects.get(pk=pid, tenant=tenant) if tenant else Product.objects.get(pk=pid)
                    new_images.append(get_image_url_from_product(prod) or '')
                except Product.DoesNotExist:
                    new_images.append('')
        else:
            for name in names:
                if not name:
                    new_images.append('')
                    continue
                prod = (
                    Product.objects.filter(name__iexact=name, tenant=tenant).first()
                    if tenant else
                    Product.objects.filter(name__iexact=name).first()
                )
                new_images.append(get_image_url_from_product(prod) if prod else '')
        if len(new_images) == 1:
            new_images.append('')
        combo['images'] = new_images
        item.combination_details = combo
        if persist:
            try:
                item.save(update_fields=['combination_details'])
            except Exception:
                pass


def get_or_create_cart(request):
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(tenant=request.tenant, user=request.user)
    else:
        if not request.session.session_key:
            request.session.create()
        cart, _ = Cart.objects.get_or_create(
            tenant=request.tenant,
            session_key=request.session.session_key,
        )
    return cart


def format_currency(value: Decimal):
    q = value.quantize(Decimal('0.01'))
    return 'R$ ' + f'{q:.2f}'.replace('.', ',')

def get_pickup_address(tenant):
    parts = []

    if tenant.pickup_address:
        address = tenant.pickup_address

        if tenant.pickup_number:
            address += f", {tenant.pickup_number}"

        parts.append(address)

    if tenant.pickup_complement:
        parts.append(tenant.pickup_complement)

    neighborhood_city = []

    if tenant.pickup_neighborhood:
        neighborhood_city.append(tenant.pickup_neighborhood)

    if tenant.pickup_city:
        neighborhood_city.append(tenant.pickup_city)

    if neighborhood_city:
        parts.append(" - ".join(neighborhood_city))

    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Delivery Fee API
# ---------------------------------------------------------------------------

@require_GET
def delivery_fee_api(request):
    """
    Confirma se cidade/bairro pertencem à área comercial da loja.

    Esta mesma regra é usada novamente no POST do checkout, então o frontend
    nunca é a fonte da verdade para taxa ou disponibilidade de entrega.
    """
    city = request.GET.get("city", "").strip()
    neighborhood = request.GET.get("neighborhood", "").strip()

    result = resolve_delivery(
        tenant=request.tenant,
        delivery_type="delivery",
        city=city,
        neighborhood=neighborhood,
    )

    return JsonResponse(
        delivery_result_to_json(result)
    )


# ---------------------------------------------------------------------------
# Cart Notes
# ---------------------------------------------------------------------------

@require_POST
def update_cart_item_notes(request, cart_item_id):
    try:
        cart = get_or_create_cart(request)
    except Exception:
        cart = None

    cart_item = (
        get_object_or_404(CartItem, pk=cart_item_id, cart=cart)
        if cart else
        get_object_or_404(CartItem, pk=cart_item_id)
    )

    notes = request.POST.get('notes', '').strip()
    try:
        cart_item.notes = notes
        cart_item.save(update_fields=['notes'])
    except Exception as exc:
        logger.exception("Erro ao salvar observação do cart_item %s: %s", cart_item_id, exc)
        return JsonResponse({"success": False, "error": "erro_salvar"}, status=500)

    return JsonResponse({"success": True, "notes": cart_item.notes})


# ---------------------------------------------------------------------------
# Add to Cart (produto simples)
# ---------------------------------------------------------------------------

@require_POST
def add_to_cart(request):
    data = {}
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)
    else:
        data = request.POST

    is_half = data.get('is_half') in (True, 'true', 'True', '1', 1)
    try:
        quantity = int(data.get('quantity', 1))
    except Exception:
        quantity = 1

    notes = get_notes_from_payload(data)
    cart  = get_or_create_cart(request)

    if is_half:
        product_ids = data.get('product_ids') or []
        if isinstance(product_ids, str):
            product_ids = [p.strip() for p in product_ids.split(',') if p.strip()]

        if not isinstance(product_ids, (list, tuple)) or len(product_ids) != 2:
            return JsonResponse({'success': False, 'error': 'É preciso escolher exatamente 2 sabores'}, status=400)

        try:
            p1 = Product.objects.get(id=product_ids[0], tenant=request.tenant, is_available=True)
            p2 = Product.objects.get(id=product_ids[1], tenant=request.tenant, is_available=True)
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Um dos sabores não encontrado'}, status=404)

        try:
            rule   = CombinationPricingRule.objects.get(tenant=request.tenant, combination_type='half_half')
            method = rule.price_calculation_method
        except CombinationPricingRule.DoesNotExist:
            method = 'max_price'

        price_a    = to_decimal(p1.sale_price if p1.sale_price else p1.price)
        price_b    = to_decimal(p2.sale_price if p2.sale_price else p2.price)
        unit_price = max(price_a, price_b) if method == 'max_price' else (price_a + price_b) / Decimal(2)

        customizations_whole = normalize_customization_list(data.get('customizations_whole') or [])
        customizations_half1 = normalize_customization_list(data.get('customizations_half1') or [])
        customizations_half2 = normalize_customization_list(data.get('customizations_half2') or [])
        notes_half1 = (data.get('notes_half1') or '').strip()
        notes_half2 = (data.get('notes_half2') or '').strip()

        unit_price += (
            sum_customizations_price(customizations_whole)
            + sum_customizations_price(customizations_half1)
            + sum_customizations_price(customizations_half2)
        )

        ids_sorted = sorted([str(p1.id), str(p2.id)], key=int)
        name       = f"{p1.name} / {p2.name}"
        images     = [get_image_url_from_product(p1), get_image_url_from_product(p2)]

        combination_details = {
            'product_ids':          ids_sorted,
            'names':                [p1.name, p2.name],
            'images':               images,
            'customizations_whole': customizations_whole,
            'customizations_half1': customizations_half1,
            'customizations_half2': customizations_half2,
            'notes_half1':          notes_half1,
            'notes_half2':          notes_half2,
        }
        key_payload = {
            'type':                 'half_half',
            'product_ids':          ids_sorted,
            'customizations_whole': customizations_whole,
            'customizations_half1': customizations_half1,
            'customizations_half2': customizations_half2,
            'notes_half1':          notes_half1,
            'notes_half2':          notes_half2,
            'notes':                notes,
        }
        product_key = build_cart_item_key(f'half:{ids_sorted[0]}:{ids_sorted[1]}', key_payload)

        defaults = {
            'name': name, 'price': unit_price, 'quantity': quantity,
            'combination_details': combination_details,
        }
        if notes:
            defaults['notes'] = notes

        cart_item, created = CartItem.objects.get_or_create(cart=cart, product_key=product_key, defaults=defaults)
        if not created:
            cart_item.quantity            += quantity
            cart_item.price               = unit_price
            cart_item.combination_details = combination_details
            update_fields = ['quantity', 'price', 'combination_details']
            if notes:
                cart_item.notes = notes
                update_fields.append('notes')
            cart_item.save(update_fields=update_fields)

        product_label = name

    else:
        product_id = data.get('product_id')
        if not product_id:
            return JsonResponse({'success': False, 'error': 'product_id ausente'}, status=400)

        product    = get_object_or_404(Product, id=product_id, tenant=request.tenant, is_available=True)
        base_price = to_decimal(product.sale_price if product.sale_price else product.price)
        customizations = normalize_customization_list(data.get('customizations') or [])
        unit_price = base_price + sum_customizations_price(customizations)

        combination_details = {'customizations': customizations} if customizations else {}
        key_payload  = {'type': 'single_product', 'product_id': str(product.id), 'customizations': customizations, 'notes': notes}
        product_key  = build_cart_item_key(f'product:{product.id}', key_payload)

        defaults = {
            'product': product, 'name': product.name, 'price': unit_price,
            'quantity': quantity, 'product_key': product_key, 'combination_details': combination_details,
        }
        if notes:
            defaults['notes'] = notes

        cart_item, created = CartItem.objects.get_or_create(cart=cart, product_key=product_key, defaults=defaults)
        if not created:
            cart_item.quantity            += quantity
            cart_item.price               = unit_price
            cart_item.combination_details = combination_details
            update_fields = ['quantity', 'price', 'combination_details']
            if notes:
                cart_item.notes = notes
                update_fields.append('notes')
            cart_item.save(update_fields=update_fields)

        product_label = product.name

    total_items = (
        cart.items
        .aggregate(total=Sum('quantity'))['total']
        or 0
    )

    subtotal = sum(
        (
            item.get_total_price()
            for item in cart.items.all()
        ),
        Decimal('0.00'),
    )

    cart_summary = cart_summary_json(
        request,
        subtotal=subtotal,
        total_items=total_items,
    )

    return JsonResponse({
        'success': True,
        'message': f'{product_label} adicionado!',
        'cart_count': int(total_items),

        # Compatibilidade com o frontend atual:
        # cart_total continua existindo, mas agora representa
        # o total comercial considerando o endereço global.
        'cart_total': cart_summary['total'],

        **cart_summary,
    })


# ---------------------------------------------------------------------------
# Cart View
# ---------------------------------------------------------------------------

def cart_view(request):
    cart = get_or_create_cart(request)

    items_qs = (
        cart.items
        .select_related('product')
        .all()
    )

    items = list(items_qs)

    populate_combination_images_for_items(
        items,
        tenant=request.tenant,
        persist=False,
    )

    populate_cart_item_price_breakdown(
        items
    )

    populate_customization_removal_flags(items)

    subtotal = sum(
        (
            item.get_total_price()
            for item in items
        ),
        Decimal('0.00'),
    )

    summary = get_cart_delivery_summary(
        request,
        subtotal=subtotal,
    )

    return render(
        request,
        'checkout/cart.html',
        {
            'cart_items': items,
            'subtotal': float(subtotal),

            # Mantemos estes nomes para compatibilidade
            # com o template atual.
            'delivery_fee': float(
                summary['delivery_fee']
            ),
            'total': float(summary['total']),

            # Novos campos do carrinho consciente
            # do endereço global.
            'cart_delivery': summary,
            'delivery_fee_display': (
                summary['delivery_fee_display']
            ),
            'delivery_available': (
                summary['delivery_available']
            ),
            'cart_can_checkout': (
                summary['can_checkout']
            ),
            'cart_checkout_mode_hint': (
                summary['checkout_mode_hint']
            ),
            'global_delivery_location': (
                summary['location']
            ),
        },
    )


# ---------------------------------------------------------------------------
# Remove / Update quantity
# ---------------------------------------------------------------------------

@require_POST
def remove_from_cart(
    request,
    cart_item_id=None,
    product_id=None,
):
    cid = cart_item_id or product_id

    if not cid:
        return JsonResponse(
            {
                'success': False,
                'error': 'cart_item_id ausente',
            },
            status=400,
        )

    cart = get_or_create_cart(request)

    deleted_count, _ = (
        CartItem.objects
        .filter(
            cart=cart,
            id=cid,
        )
        .delete()
    )

    items = (
        cart.items
        .select_related('product')
        .all()
    )

    subtotal = sum(
        (
            item.get_total_price()
            for item in items
        ),
        Decimal('0.00'),
    )

    total_items = sum(
        item.quantity
        for item in items
    )

    summary = cart_summary_json(
        request,
        subtotal=subtotal,
        total_items=total_items,
    )

    return JsonResponse({
        'success': True,
        'deleted': int(deleted_count),

        # Mantido para compatibilidade com JS antigo.
        'total': summary['total_display'],

        **summary,
    })


@require_POST
@transaction.atomic
def remove_cart_item_customization(request, cart_item_id):
    cart = get_or_create_cart(request)

    try:
        data = json.loads(request.body.decode('utf-8') or '{}') if request.content_type == 'application/json' else request.POST
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Dados inválidos.'}, status=400)

    bucket = str(data.get('bucket', '') or '').strip()

    try:
        index = int(data.get('index'))
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Opcional inválido.'}, status=400)

    if bucket not in CUSTOMIZATION_BUCKETS:
        return JsonResponse({'success': False, 'error': 'Grupo de opcionais inválido.'}, status=400)

    cart_item = get_object_or_404(CartItem.objects.select_for_update(), cart=cart, id=cart_item_id)

    combo = dict(cart_item.combination_details or {})
    customizations = list(combo.get(bucket) or [])

    if index < 0 or index >= len(customizations):
        return JsonResponse({'success': False, 'error': 'Opcional não encontrado no carrinho.'}, status=404)

    if not customization_can_be_removed(customizations, index):
        group_name = str(customizations[index].get('group_name', '') or 'este grupo')
        return JsonResponse(
            {'success': False, 'error': f'Não é possível remover esta opção. O grupo "{group_name}" possui uma quantidade mínima obrigatória.'},
            status=400,
        )

    breakdown_before = get_cart_item_price_breakdown(cart_item)
    base_unit_price = breakdown_before['base_unit_price']
    removed = customizations.pop(index)
    combo[bucket] = customizations

    remaining_additions = sum_customizations_price(get_all_customizations_from_combo(combo))
    new_unit_price = (base_unit_price + remaining_additions).quantize(Decimal('0.01'))
    new_product_key = rebuild_cart_item_key(cart_item, combo)

    duplicate = (
        CartItem.objects
        .select_for_update()
        .filter(cart=cart, product_key=new_product_key)
        .exclude(pk=cart_item.pk)
        .first()
    )

    merged = duplicate is not None

    if duplicate:
        duplicate.quantity += cart_item.quantity
        duplicate.price = new_unit_price
        duplicate.combination_details = combo
        duplicate.save(update_fields=['quantity', 'price', 'combination_details'])
        cart_item.delete()
        updated_item = duplicate
    else:
        cart_item.price = new_unit_price
        cart_item.combination_details = combo
        cart_item.product_key = new_product_key
        cart_item.save(update_fields=['price', 'combination_details', 'product_key'])
        updated_item = cart_item

    items = list(cart.items.select_related('product').all())
    subtotal = sum((item.get_total_price() for item in items), Decimal('0.00'))
    total_items = sum(item.quantity for item in items)
    summary = cart_summary_json(request, subtotal=subtotal, total_items=total_items)

    return JsonResponse({
        'success': True,
        'message': f'{removed.get("option_name") or "Opcional"} removido.',
        'removed': {
            'group_name': str(removed.get('group_name', '') or ''),
            'option_name': str(removed.get('option_name', '') or ''),
            'price': str(to_decimal(removed.get('price', 0)).quantize(Decimal('0.01'))),
        },
        'merged': merged,
        'reload_required': merged,
        **cart_item_prices_json(updated_item),
        **summary,
    })


@require_POST
def update_cart_quantity(
    request,
    cart_item_id,
):
    cart = get_or_create_cart(request)

    if request.content_type == 'application/json':
        try:
            data = json.loads(
                request.body.decode('utf-8')
                or '{}'
            )
            quantity = int(
                data.get('quantity', 0)
            )
        except Exception:
            return JsonResponse(
                {
                    'success': False,
                    'error': 'JSON inválido',
                },
                status=400,
            )
    else:
        quantity = int(
            request.POST.get('quantity', 0)
        )

    try:
        cart_item = CartItem.objects.get(
            cart=cart,
            id=cart_item_id,
        )

        if quantity <= 0:
            cart_item.delete()

        else:
            cart_item.quantity = quantity
            cart_item.save(
                update_fields=['quantity']
            )

        items = (
            cart.items
            .select_related('product')
            .all()
        )

        subtotal = sum(
            (
                item.get_total_price()
                for item in items
            ),
            Decimal('0.00'),
        )

        total_items = sum(
            item.quantity
            for item in items
        )

        summary = cart_summary_json(
            request,
            subtotal=subtotal,
            total_items=total_items,
        )

        return JsonResponse({
            'success': True,

            # Mantido para compatibilidade com JS antigo.
            'total': summary['total_display'],

            **summary,
        })

    except CartItem.DoesNotExist:
        return JsonResponse(
            {
                'success': False,
                'error': 'Item não encontrado',
            },
            status=404,
        )


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

@transaction.atomic
def checkout_step_one(request):
    cart = get_or_create_cart(request)
    cart_items = cart.items.select_related('product')

    checkout_token = request.session.get(
        "checkout_token"
    )

    if not checkout_token:
        checkout_token = str(uuid.uuid4())
        request.session[
            "checkout_token"
        ] = checkout_token
        request.session.modified = True

    # -----------------------------------------------------------------------
    # Cliente autenticado + endereços salvos
    # -----------------------------------------------------------------------
    customer = None
    customer_addresses = CustomerAddress.objects.none()
    default_address = None
    global_delivery_location = get_global_delivery_location(request)
    use_global_manual_address = bool(
        global_delivery_location
        and global_delivery_location.get("source") == "manual"
    )

    if request.user.is_authenticated:
        customer = (
            Customer.objects
            .filter(user=request.user)
            .first()
        )

        if customer:
            customer_addresses = (
                customer.addresses
                .all()
                .order_by('-is_default', '-created_at')
            )

            if (
                global_delivery_location
                and global_delivery_location.get("source") == "saved"
                and global_delivery_location.get("customer_address_id")
            ):
                default_address = (
                    customer_addresses
                    .filter(
                        pk=global_delivery_location[
                            "customer_address_id"
                        ]
                    )
                    .first()
                )

            if default_address is None and not use_global_manual_address:
                default_address = (
                    customer_addresses
                    .filter(is_default=True)
                    .first()
                )

            if default_address is None and not use_global_manual_address:
                default_address = customer_addresses.first()

    if not cart_items.exists():
        messages.warning(request, "Seu carrinho está vazio.")
        return redirect('stores:catalogo')

    subtotal = sum(
        (item.get_total_price() for item in cart_items),
        Decimal('0.00'),
    )

    delivery_zones = (
        DeliveryZone.objects
        .filter(
            tenant=request.tenant,
            is_active=True,
        )
        .values(
            'city',
            'neighborhood',
            'fee',
        )
        .order_by(
            'city',
            'neighborhood',
        )
    )

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        payment_method = request.POST.get('payment_method', '').strip()
        change_for = request.POST.get('change_for', '').strip()
        delivery_type = request.POST.get('delivery_type', '').strip()
        coupon_code = request.POST.get('coupon_code', '').strip().upper()
        posted_checkout_token = (
            request.POST.get(
                "checkout_token",
                "",
            ).strip()
        )

        if (
            not posted_checkout_token
            or posted_checkout_token
            != str(checkout_token)
        ):
            return HttpResponseBadRequest(
                "Sessão de checkout inválida. Atualize a página e tente novamente."
            )

        existing_order = (
            Order.objects
            .filter(
                tenant=request.tenant,
                checkout_token=posted_checkout_token,
                abandoned_at__isnull=True,
            )
            .prefetch_related("items")
            .first()
        )

        if existing_order is not None:
            return render(
                request,
                "checkout/review.html",
                {
                    "order": existing_order,
                },
            )

        if not full_name:
            return HttpResponseBadRequest('Informe o nome do cliente.')

        if not phone:
            return HttpResponseBadRequest('Informe o telefone do cliente.')

        if delivery_type not in ('delivery', 'pickup'):
            return HttpResponseBadRequest('Tipo de recebimento inválido.')

        if delivery_type == 'delivery' and not request.tenant.accepts_delivery:
            return HttpResponseBadRequest(
                'Esta loja não aceita pedidos para entrega.'
            )

        if delivery_type == 'pickup' and not request.tenant.accepts_pickup:
            return HttpResponseBadRequest(
                'Esta loja não aceita pedidos para retirada.'
            )

        customer_address = None

        if customer and delivery_type == 'delivery':
            customer_address_id = request.POST.get(
                'customer_address_id',
                '',
            ).strip()

            if customer_address_id:
                customer_address = (
                    CustomerAddress.objects
                    .filter(
                        pk=customer_address_id,
                        customer=customer,
                    )
                    .first()
                )

                if customer_address is None:
                    return HttpResponseBadRequest(
                        'O endereço selecionado é inválido.'
                    )

        zip_code = ''
        address = ''
        number = ''
        neighborhood = ''
        city = ''
        state = ''
        complement = ''
        reference = ''

        if delivery_type == 'pickup':
            delivery_fee = Decimal('0.00')
            fee_label = 'Retirada na loja'
            delivery_address = get_pickup_address(request.tenant)
            city_line = ''

            if not delivery_address:
                return HttpResponseBadRequest(
                    'O endereço de retirada da loja não está configurado.'
                )

        else:
            if customer_address:
                zip_code = customer_address.zip_code
                address = customer_address.street
                number = customer_address.number
                neighborhood = customer_address.neighborhood
                city = customer_address.city
                state = customer_address.state
                complement = customer_address.complement
                reference = customer_address.reference

            else:
                zip_code = request.POST.get('cep', '').strip()
                address = request.POST.get('address', '').strip()
                number = request.POST.get('number', '').strip()
                neighborhood = request.POST.get('neighborhood', '').strip()
                city = request.POST.get('city', '').strip()
                state = request.POST.get('state', '').strip().upper()
                complement = request.POST.get('complement', '').strip()
                reference = request.POST.get('reference', '').strip()

            if not address or not number or not neighborhood or not city:
                return HttpResponseBadRequest(
                    'Informe rua, número, bairro e cidade para entrega.'
                )

            delivery_result = resolve_delivery(
                tenant=request.tenant,
                delivery_type='delivery',
                city=city,
                neighborhood=neighborhood,
            )

            if not delivery_result['available']:
                return HttpResponseBadRequest(
                    delivery_result['message']
                    or 'Esta loja não entrega no endereço informado.'
                )

            delivery_fee = delivery_result['fee']
            fee_label = delivery_result['fee_display']

            delivery_address = f"{address}, {number}"

            if complement:
                delivery_address += f", {complement}"

            city_line_parts = []

            if neighborhood:
                city_line_parts.append(neighborhood)

            city_state = city

            if state:
                city_state += f"/{state}"

            if city_state:
                city_line_parts.append(city_state)

            if zip_code:
                city_line_parts.append(f"CEP {zip_code}")

            city_line = ", ".join(city_line_parts)

            if reference:
                city_line += f"\nPonto de referência: {reference}"

        if delivery_type == 'delivery':
            if customer_address is not None:
                set_global_delivery_location(
                    request,
                    serialize_customer_address(
                        customer_address
                    ),
                )
            else:
                set_global_delivery_location(
                    request,
                    serialize_manual_address(
                        {
                            "zip_code": zip_code,
                            "street": address,
                            "number": number,
                            "complement": complement,
                            "neighborhood": neighborhood,
                            "city": city,
                            "state": state,
                            "reference": reference,
                        }
                    ),
                )

        applied_campaign = None
        discount_amount = Decimal('0.00')

        if coupon_code:
            # Bloqueia a campanha durante a finalização do checkout.
            #
            # O checkout já está dentro de @transaction.atomic. Portanto,
            # o select_for_update() mantém a linha da campanha bloqueada
            # até o commit/rollback da transação. Isso impede que dois
            # pedidos simultâneos consumam a última utilização do cupom.
            locked_campaign = (
                CouponCampaign.objects
                .select_for_update()
                .filter(
                    tenant=request.tenant,
                    code__iexact=coupon_code,
                )
                .first()
            )

            if locked_campaign is None:
                return HttpResponseBadRequest('Cupom inválido.')

            # Revalida somente depois de obter o lock.
            # Assim, limites total/por cliente são calculados já considerando
            # qualquer checkout concorrente que tenha terminado antes deste.
            coupon_result = validate_coupon(
                code=locked_campaign.code,
                tenant=request.tenant,
                customer=customer,
                subtotal=subtotal,
                delivery_fee=delivery_fee,
            )

            if not coupon_result["valid"]:
                return HttpResponseBadRequest(coupon_result["message"])

            applied_campaign = locked_campaign
            discount_amount = to_decimal(coupon_result["discount"])
            total = to_decimal(coupon_result["final_total"])
        else:
            total = subtotal + delivery_fee

        payment_labels = {
            'cash': 'Dinheiro',
            'credit_card': 'Cartão de Crédito',
            'debit_card': 'Cartão de Débito',
            'pix': 'PIX',
        }

        payment_label = payment_labels.get(
            payment_method,
            payment_method,
        )

        payment_info = (
            f"Dinheiro (troco para R$ {change_for})"
            if payment_method == 'cash' and change_for
            else payment_label
        )

        order_data = {
            'tenant': request.tenant,
            'customer': customer,
            'customer_name': full_name,
            'customer_phone': phone,
            'subtotal': subtotal,
            'delivery_fee': delivery_fee,
            'coupon_code': applied_campaign.code if applied_campaign else '',
            'discount_amount': discount_amount,
            'total': total,
            'delivery_type': delivery_type,
            'payment_method': payment_method,
            'payment_change_for': change_for,
            'checkout_token': posted_checkout_token,
            'source_cart_id': cart.id,
        }

        if delivery_type == 'delivery':
            order_data.update({
                'delivery_zip_code': zip_code,
                'delivery_street': address,
                'delivery_number': number,
                'delivery_complement': complement,
                'delivery_neighborhood': neighborhood,
                'delivery_city': city,
                'delivery_state': state,
                'delivery_reference': reference,
            })

        order = Order.objects.create(**order_data)

        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item.product,
                name=item.name,
                price=item.price,
                quantity=item.quantity,
                combination_details=item.combination_details,
                product_key=item.product_key or "",
                notes=item.notes or "",
            )

        if applied_campaign:
            CouponRedemption.objects.create(
                campaign=applied_campaign,
                customer=customer,
                order=order,
                discount_amount=discount_amount,
            )

        return render(
            request,
            "checkout/review.html",
            {
                "order": order,
            },
        )

    def build_item_context(item):
        combo = item.combination_details or {}

        customizations = (
            combo.get('customizations')
            or (
                combo.get('customizations_whole', [])
                + combo.get('customizations_half1', [])
                + combo.get('customizations_half2', [])
            )
        )

        price_breakdown = get_cart_item_price_breakdown(
            item
        )

        return {
            'id': item.product.id if item.product else None,
            'name': item.name,

            # Compatibilidade com o template/JS atual.
            'price': float(
                price_breakdown['final_unit_price']
            ),
            'quantity': item.quantity,
            'total_price': float(
                price_breakdown['line_total']
            ),

            # Novo detalhamento de preço.
            'base_unit_price': float(
                price_breakdown['base_unit_price']
            ),
            'additions_unit_price': float(
                price_breakdown['additions_unit_price']
            ),
            'final_unit_price': float(
                price_breakdown['final_unit_price']
            ),
            'base_total': float(
                price_breakdown['base_total']
            ),
            'additions_total': float(
                price_breakdown['additions_total']
            ),
            'line_total': float(
                price_breakdown['line_total']
            ),
            'has_additions': price_breakdown[
                'has_additions'
            ],

            'notes': item.notes or '',
            'customizations': customizations,
            'is_half_half': bool(
                combo.get('product_ids')
            ),
            'names': combo.get('names', []),
            'customizations_whole': combo.get(
                'customizations_whole',
                [],
            ),
            'customizations_half1': combo.get(
                'customizations_half1',
                [],
            ),
            'customizations_half2': combo.get(
                'customizations_half2',
                [],
            ),
            'notes_half1': combo.get(
                'notes_half1',
                '',
            ),
            'notes_half2': combo.get(
                'notes_half2',
                '',
            ),
        }

    initial_full_name = ''
    initial_phone = ''

    if customer:
        initial_full_name = (
            request.user.get_full_name()
            or request.user.username
        )
        initial_phone = customer.phone or ''

    return render(
        request,
        'checkout/checkout.html',
        {
            'cart_items': [
                build_item_context(item)
                for item in cart_items
            ],
            'subtotal': float(subtotal),
            'total': float(subtotal),
            'delivery_zones': list(delivery_zones),
            'store_address': get_pickup_address(request.tenant),
            'customer': customer,
            'customer_addresses': customer_addresses,
            'default_address': default_address,
            'global_delivery_location': global_delivery_location,
            'use_global_manual_address': use_global_manual_address,
            'initial_full_name': initial_full_name,
            'initial_phone': initial_phone,
            'checkout_token': checkout_token,
        },
    )


def order_success(request):
    return render(request, 'checkout/order_success.html')


# ---------------------------------------------------------------------------
# Add Half-Half
# ---------------------------------------------------------------------------

@require_POST
def add_half_half(request):
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.content_type == 'application/json' else request.POST
    except Exception:
        payload = request.POST

    if hasattr(payload, 'getlist'):
        product_ids = payload.get('product_ids') or payload.getlist('product_ids[]') or payload.getlist('product_ids')
    else:
        product_ids = payload.get('product_ids') or payload.get('product_ids[]')

    if isinstance(product_ids, str):
        product_ids = [p.strip() for p in product_ids.split(',') if p.strip()]

    try:
        quantity = max(1, int(payload.get('quantity', 1)))
    except Exception:
        quantity = 1

    notes       = get_notes_from_payload(payload)
    notes_half1 = (payload.get('notes_half1') or '').strip()
    notes_half2 = (payload.get('notes_half2') or '').strip()

    if not product_ids or not isinstance(product_ids, (list, tuple)) or len(product_ids) != 2:
        return JsonResponse({'success': False, 'error': _('É necessário fornecer exatamente dois sabores.')}, status=400)

    if str(product_ids[0]) == str(product_ids[1]):
        return JsonResponse({'success': False, 'error': _('Escolha dois sabores diferentes para montar meio a meio.')}, status=400)

    try:
        p1 = Product.objects.get(pk=product_ids[0], tenant=request.tenant, is_available=True)
        p2 = Product.objects.get(pk=product_ids[1], tenant=request.tenant, is_available=True)
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': _('Um dos produtos não foi encontrado.')}, status=404)

    try:
        rule   = CombinationPricingRule.objects.get(tenant=request.tenant, combination_type='half_half')
        method = rule.price_calculation_method
    except CombinationPricingRule.DoesNotExist:
        method = 'max_price'

    price_a    = to_decimal(p1.sale_price if p1.sale_price else p1.price)
    price_b    = to_decimal(p2.sale_price if p2.sale_price else p2.price)
    unit_price = max(price_a, price_b) if method == 'max_price' else (price_a + price_b) / Decimal(2)

    customizations_whole = normalize_customization_list(payload.get('customizations_whole') or [])
    customizations_half1 = normalize_customization_list(payload.get('customizations_half1') or [])
    customizations_half2 = normalize_customization_list(payload.get('customizations_half2') or [])

    unit_price += (
        sum_customizations_price(customizations_whole)
        + sum_customizations_price(customizations_half1)
        + sum_customizations_price(customizations_half2)
    )

    ids_sorted = sorted([str(p1.id), str(p2.id)], key=int)
    name       = f"{p1.name} / {p2.name} (Meio a meio)"
    images     = [get_image_url_from_product(p1), get_image_url_from_product(p2)]

    combination_details = {
        'product_ids':          ids_sorted,
        'names':                [p1.name, p2.name],
        'images':               images,
        'customizations_whole': customizations_whole,
        'customizations_half1': customizations_half1,
        'customizations_half2': customizations_half2,
        'notes_half1':          notes_half1,
        'notes_half2':          notes_half2,
    }
    key_payload = {
        'type':                 'half_half',
        'product_ids':          ids_sorted,
        'customizations_whole': customizations_whole,
        'customizations_half1': customizations_half1,
        'customizations_half2': customizations_half2,
        'notes_half1':          notes_half1,
        'notes_half2':          notes_half2,
        'notes':                notes,
    }
    product_key = build_cart_item_key(f'half:{ids_sorted[0]}:{ids_sorted[1]}', key_payload)

    cart = get_or_create_cart(request)

    defaults = {
        'name': name, 'price': unit_price, 'quantity': quantity,
        'combination_details': combination_details, 'product_key': product_key,
    }
    if notes:
        defaults['notes'] = notes

    cart_item, created = CartItem.objects.get_or_create(cart=cart, product_key=product_key, defaults=defaults)
    if not created:
        cart_item.quantity            += quantity
        cart_item.price               = unit_price
        cart_item.combination_details = combination_details
        update_fields = ['quantity', 'price', 'combination_details']
        if notes:
            cart_item.notes = notes
            update_fields.append('notes')
        cart_item.save(update_fields=update_fields)

    total_items = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
    cart_total  = sum((item.price * item.quantity) for item in cart.items.all())

    return JsonResponse({
        'success':    True,
        'added':      True,
        'message':    f"Pizza meio a meio adicionada. Será cobrado {format_currency(unit_price)} por unidade.",
        'cart_count': int(total_items),
        'cart_total': str(cart_total),
    })
