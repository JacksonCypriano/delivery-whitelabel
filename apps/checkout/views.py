# apps/checkout/views.py
import hashlib
import json
import logging
import urllib.parse
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.orders.models import Cart, CartItem, CombinationPricingRule, Order, OrderItem
from apps.stores.models import Product
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


def get_notes_from_payload(data):
    return (data.get('notes') or data.get('note') or '').strip()


def normalize_customization_list(raw_list):
    if not isinstance(raw_list, (list, tuple)):
        return []
    normalized = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        price = to_decimal(item.get('price', 0))
        normalized.append({
            'group_id':    str(item.get('group_id',    '') or ''),
            'group_name':  str(item.get('group_name',  '') or ''),
            'option_id':   str(item.get('option_id',   '') or ''),
            'option_name': str(item.get('option_name', '') or ''),
            'price':       str(price),
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

def resolve_delivery_fee(tenant, delivery_type, city, neighborhood):
    """
    Retorna (fee: Decimal, label: str).
    Prioridade: 1) pickup → grátis; 2) DeliveryZone ativa; 3) taxa padrão do tenant.
    """
    if delivery_type == 'pickup':
        return Decimal('0.00'), 'Retirada na loja'

    if city and neighborhood:
        zone = DeliveryZone.objects.filter(
            tenant=tenant,
            city__iexact=city,
            neighborhood__iexact=neighborhood,
            is_active=True,
        ).first()
        if zone:
            return zone.fee, f'R$ {zone.fee:.2f}'.replace('.', ',')

    # fallback: taxa padrão do tenant
    fallback = to_decimal(getattr(tenant, 'delivery_fee', None))
    if fallback > 0:
        return fallback, f'R$ {fallback:.2f}'.replace('.', ',') + ' (padrão)'

    return Decimal('0.00'), 'Grátis'


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

    total_items = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
    cart_total  = sum((item.get_total_price() for item in cart.items.all()), Decimal('0.00'))

    return JsonResponse({
        'success':    True,
        'message':    f'{product_label} adicionado!',
        'cart_count': int(total_items),
        'cart_total': str(cart_total),
    })


# ---------------------------------------------------------------------------
# Cart View
# ---------------------------------------------------------------------------

def cart_view(request):
    cart     = get_or_create_cart(request)
    items_qs = cart.items.select_related('product').all()
    items    = list(items_qs)

    populate_combination_images_for_items(items, tenant=request.tenant, persist=False)

    subtotal     = sum((item.get_total_price() for item in items), Decimal('0.00'))
    delivery_fee = to_decimal(getattr(request.tenant, 'delivery_fee', 0) or 0)
    total        = subtotal + delivery_fee if items else Decimal('0.00')

    return render(request, 'checkout/cart.html', {
        'cart_items':   items,
        'subtotal':     float(subtotal),
        'delivery_fee': float(delivery_fee),
        'total':        float(total),
    })


# ---------------------------------------------------------------------------
# Remove / Update quantity
# ---------------------------------------------------------------------------

@require_POST
def remove_from_cart(request, cart_item_id=None, product_id=None):
    cid = cart_item_id or product_id
    if not cid:
        return JsonResponse({'success': False, 'error': 'cart_item_id ausente'}, status=400)

    cart = get_or_create_cart(request)
    deleted_count, _ = CartItem.objects.filter(cart=cart, id=cid).delete()

    items       = cart.items.select_related('product').all()
    subtotal    = sum((item.get_total_price() for item in items), Decimal('0.00'))
    total_items = sum(item.quantity for item in items)

    return JsonResponse({
        'success':    True,
        'deleted':    int(deleted_count),
        'total':      f'R$ {subtotal:.2f}'.replace('.', ','),
        'cart_count': int(total_items),
    })


@require_POST
def update_cart_quantity(request, cart_item_id):
    cart = get_or_create_cart(request)
    if request.content_type == 'application/json':
        try:
            data     = json.loads(request.body.decode('utf-8') or '{}')
            quantity = int(data.get('quantity', 0))
        except Exception:
            return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)
    else:
        quantity = int(request.POST.get('quantity', 0))

    try:
        cart_item = CartItem.objects.get(cart=cart, id=cart_item_id)
        if quantity <= 0:
            cart_item.delete()
        else:
            cart_item.quantity = quantity
            cart_item.save()

        items       = cart.items.select_related('product').all()
        subtotal    = sum((item.get_total_price() for item in items), Decimal('0.00'))
        total_items = sum(item.quantity for item in items)

        return JsonResponse({
            'success':    True,
            'total':      f'R$ {subtotal:.2f}'.replace('.', ','),
            'cart_count': int(total_items),
        })
    except CartItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item não encontrado'}, status=404)


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

@transaction.atomic
def checkout_step_one(request):
    cart       = get_or_create_cart(request)
    cart_items = cart.items.select_related('product')

    if not cart_items.exists():
        messages.warning(request, "Seu carrinho está vazio.")
        return redirect('stores:catalogo')

    subtotal = sum(item.get_total_price() for item in cart_items)

    # Zonas ativas do tenant (usadas no GET e no POST)
    delivery_zones = (
        DeliveryZone.objects
        .filter(tenant=request.tenant, is_active=True)
        .values('city', 'neighborhood', 'fee')
        .order_by('city', 'neighborhood')
    )

    if request.method == 'POST':
        full_name      = request.POST.get('full_name', '').strip()
        phone          = request.POST.get('phone', '').strip()
        payment_method = request.POST.get('payment_method', '')
        change_for     = request.POST.get('change_for', '').strip()
        delivery_type  = request.POST.get('delivery_type', '').strip()

        # ── Validação do modo de atendimento da loja ────────────────────────
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

        # ── Endereço e frete ────────────────────────────────────────────────
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
            zip_code     = request.POST.get('cep', '').strip()
            address      = request.POST.get('address', '').strip()
            number       = request.POST.get('number', '').strip()
            neighborhood = request.POST.get('neighborhood', '').strip()
            city         = request.POST.get('city', '').strip()
            complement   = request.POST.get('complement', '').strip()

            if not address or not number or not neighborhood or not city:
                return HttpResponseBadRequest(
                    'Informe rua, número, bairro e cidade para entrega.'
                )

            # Busca a taxa pelo DeliveryZone cadastrado
            delivery_fee, fee_label = resolve_delivery_fee(
                request.tenant, 'delivery', city, neighborhood
            )

            delivery_address = f"{address}, {number}"
            if complement:
                delivery_address += f", {complement}"
            city_line = f"{neighborhood}, {city}, CEP {zip_code}" if neighborhood or city else ''

        total = subtotal + delivery_fee

        # ── Pagamento ───────────────────────────────────────────────────────
        payment_labels = {
            'cash':        'Dinheiro',
            'credit_card': 'Cartão de Crédito',
            'debit_card':  'Cartão de Débito',
            'pix':         'PIX',
        }
        payment_label = payment_labels.get(payment_method, payment_method)
        payment_info  = (
            f"Dinheiro (troco para R$ {change_for})"
            if payment_method == 'cash' and change_for
            else payment_label
        )

        # ── Criação do pedido ───────────────────────────────────────────────
        order = Order.objects.create(
            tenant=request.tenant,
            customer_phone=phone,
            total=total,
        )

        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item.product,
                name=item.name,
                price=item.price,
                quantity=item.quantity,
                combination_details=item.combination_details,
            )

        # ── Formata itens para WhatsApp ─────────────────────────────────────
        def fmt_price(val):
            return f"+R$ {float(val):.2f}".replace('.', ',') if float(val or 0) > 0 else ''

        def format_item_line(item):
            combo     = item.combination_details or {}
            names     = combo.get('names', [])
            total_str = f"{item.get_total_price():.2f}".replace('.', ',')
            lines     = [f"{item.quantity}x {item.name} — R$ {total_str}"]

            for c in combo.get('customizations_whole', []):
                p = fmt_price(c.get('price', 0))
                lines.append(f"   🔸 Borda: {c.get('option_name', '')}" + (f" ({p})" if p else ''))

            name1 = names[0] if names else 'Metade 1'
            if combo.get('customizations_half1') or combo.get('notes_half1'):
                lines.append(f"   ½ {name1}")
                for c in combo.get('customizations_half1', []):
                    p = fmt_price(c.get('price', 0))
                    lines.append(f"      + {c.get('option_name', '')}" + (f" ({p})" if p else ''))
                if combo.get('notes_half1'):
                    lines.append(f"      Obs: {combo['notes_half1']}")

            name2 = names[1] if len(names) > 1 else 'Metade 2'
            if combo.get('customizations_half2') or combo.get('notes_half2'):
                lines.append(f"   ½ {name2}")
                for c in combo.get('customizations_half2', []):
                    p = fmt_price(c.get('price', 0))
                    lines.append(f"      + {c.get('option_name', '')}" + (f" ({p})" if p else ''))
                if combo.get('notes_half2'):
                    lines.append(f"      Obs: {combo['notes_half2']}")

            for c in combo.get('customizations', []):
                p = fmt_price(c.get('price', 0))
                lines.append(f"   + {c.get('group_name', '')}: {c.get('option_name', '')}" + (f" ({p})" if p else ''))

            if item.notes:
                lines.append(f"   Obs: {item.notes}")

            return '\n'.join(lines)

        sep         = '━' * 22
        items_lines = f'\n{sep}\n'.join(format_item_line(item) for item in cart_items)

        if delivery_type == 'pickup':
            totals_block = (
                f"Subtotal: R$ {subtotal:.2f}".replace('.', ',') + '\n'
                f"*Total: R$ {total:.2f}*".replace('.', ',')
            )
        else:
            totals_block = (
                f"Subtotal: R$ {subtotal:.2f}".replace('.', ',') + '\n'
                f"Taxa de entrega: {fee_label}\n"
                f"*Total: R$ {total:.2f}*".replace('.', ',')
            )

        if delivery_type == 'pickup':
            delivery_block = (
                delivery_address
                if delivery_address
                else 'Endereço de retirada não informado.'
            )
        else:
            delivery_block = (
                f"{delivery_address}\n{city_line}"
                if city_line
                else delivery_address
            )

        message = (
            f"*Novo Pedido #{order.id}*\n"
            f"{sep}\n\n"
            f"*Cliente*\n"
            f"Nome: {full_name}\n"
            f"Telefone: {phone}\n\n"
            f"*Itens*\n\n"
            f"{items_lines}\n\n"
            f"{sep}\n"
            f"{totals_block}\n"
            f"*Pagamento: {payment_info}*\n\n"
            f"*{'Retirada' if delivery_type == 'pickup' else 'Entrega'}*\n"
            f"{delivery_block}\n"
            f"{sep}"
        )

        whatsapp_number = request.tenant.whatsapp_number
        whatsapp_url    = f"https://wa.me/{whatsapp_number}?text={urllib.parse.quote(message, safe='')}"

        cart.delete()
        return redirect(whatsapp_url)

    # ── GET ──────────────────────────────────────────────────────────────────
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
        return {
            'id':                   item.product.id if item.product else None,
            'name':                 item.name,
            'price':                float(item.price),
            'quantity':             item.quantity,
            'total_price':          float(item.get_total_price()),
            'notes':                item.notes or '',
            'customizations':       customizations,
            'is_half_half':         bool(combo.get('product_ids')),
            'names':                combo.get('names', []),
            'customizations_whole': combo.get('customizations_whole', []),
            'customizations_half1': combo.get('customizations_half1', []),
            'customizations_half2': combo.get('customizations_half2', []),
            'notes_half1':          combo.get('notes_half1', ''),
            'notes_half2':          combo.get('notes_half2', ''),
        }

    return render(request, 'checkout/checkout.html', {
        'cart_items':     [build_item_context(item) for item in cart_items],
        'subtotal':       float(subtotal),
        'total':          float(subtotal),  # total sem frete; JS e POST atualizam
        'delivery_zones': list(delivery_zones),
        'store_address': get_pickup_address(request.tenant),
    })


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