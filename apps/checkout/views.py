import hashlib
import json
import logging
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

logger = logging.getLogger(__name__)
User = get_user_model()


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
    """
    Normaliza a lista vinda do frontend para um formato consistente e seguro.
    """
    if not isinstance(raw_list, (list, tuple)):
        return []

    normalized = []

    for item in raw_list:
        if not isinstance(item, dict):
            continue

        price = to_decimal(item.get('price', 0))
        normalized.append({
            'group_id': str(item.get('group_id', '') or ''),
            'group_name': str(item.get('group_name', '') or ''),
            'option_id': str(item.get('option_id', '') or ''),
            'option_name': str(item.get('option_name', '') or ''),
            'price': str(price),
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
    """
    Gera uma chave estável e curta para diferenciar itens com customizações distintas.
    """
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]
    return f'{prefix}:{digest}'


def get_image_url_from_product(product):
    """
    Retorna uma URL string da imagem principal de `product`, tentando:
    - chamar product.get_primary_image() se for chamável
    - usar .url se for FileField
    - verificar atributos comuns (image, primary_image, thumbnail)
    Retorna '' se não encontrar.
    """
    if not product:
        return ''

    # tentar método/atributo get_primary_image primeiro
    try:
        getter = getattr(product, 'get_primary_image', None)
        if callable(getter):
            val = getter()
        else:
            val = getter
        if isinstance(val, str) and val:
            return val
        if hasattr(val, 'url'):
            return val.url
    except Exception:
        pass

    # tentar campos comuns
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
    """
    Para cada CartItem em items, se existir combination_details e images vazias,
    tenta preencher images usando product_ids ou names.
    Se persist=True, salva item.combination_details de volta no DB.
    """
    for item in items:
        combo = getattr(item, 'combination_details', None)
        if not combo or not isinstance(combo, dict):
            continue

        images = combo.get('images') or []
        # se já tem pelo menos uma imagem não vazia, ignora
        if images and any(str(i).strip() for i in images):
            continue

        new_images = []
        ids = combo.get('product_ids') or []
        names = combo.get('names') or []

        # tentar preencher por product_ids
        if ids:
            for pid in ids:
                try:
                    prod = Product.objects.get(pk=pid, tenant=tenant) if tenant else Product.objects.get(pk=pid)
                    new_images.append(get_image_url_from_product(prod) or '')
                except Product.DoesNotExist:
                    new_images.append('')
        else:
            # tentar preencher por nomes
            for name in names:
                if not name:
                    new_images.append('')
                    continue
                prod = Product.objects.filter(name__iexact=name, tenant=tenant).first() if tenant else Product.objects.filter(name__iexact=name).first()
                new_images.append(get_image_url_from_product(prod) if prod else '')

        # garantir pelo menos 2 posições (mantém layout)
        if len(new_images) == 1:
            new_images.append('')

        combo['images'] = new_images
        # atualizar in-memory para o template
        item.combination_details = combo

        # opcional: persistir no DB
        if persist:
            try:
                item.combination_details = combo
                item.save(update_fields=['combination_details'])
            except Exception:
                # não quebrar renderização se falhar ao salvar
                pass


def get_or_create_cart(request):
    """Obtém ou cria carrinho para usuário anônimo ou logado"""
    if request.user.is_authenticated:
        cart, created = Cart.objects.get_or_create(
            tenant=request.tenant,
            user=request.user
        )
    else:
        # Usuário anônimo
        if not request.session.session_key:
            request.session.create()

        cart, created = Cart.objects.get_or_create(
            tenant=request.tenant,
            session_key=request.session.session_key
        )
    return cart


@require_POST
def update_cart_item_notes(request, cart_item_id):
    """
    Atualiza o campo notes (observação) de um CartItem.
    """
    try:
        cart = get_or_create_cart(request)
    except Exception:
        cart = None

    if cart:
        cart_item = get_object_or_404(CartItem, pk=cart_item_id, cart=cart)
    else:
        cart_item = get_object_or_404(CartItem, pk=cart_item_id)

    notes = request.POST.get('notes', '').strip()

    try:
        cart_item.notes = notes
        cart_item.save(update_fields=['notes'])
    except Exception as exc:
        logger.exception("Erro ao salvar observação do cart_item %s: %s", cart_item_id, exc)
        return JsonResponse({"success": False, "error": "erro_salvar"}, status=500)

    return JsonResponse({"success": True, "notes": cart_item.notes})


@require_POST
def add_to_cart(request):
    """
    Aceita:
    - form POST (product_id, quantity, notes) para item simples
    - JSON POST com { is_half: true, product_ids: [id1, id2], quantity: x, notes: "..."} para meio-a-meio
    - customizações no payload:
      - produto simples: customizations
      - meio a meio: customizations_whole, customizations_half1, customizations_half2
    Retorna JSON com success, message e cart_count.
    """
    # parse JSON body se vier JSON
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
    cart = get_or_create_cart(request)

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
            rule = CombinationPricingRule.objects.get(tenant=request.tenant, combination_type='half_half')
            method = rule.price_calculation_method
        except CombinationPricingRule.DoesNotExist:
            method = 'max_price'

        price_a = to_decimal(p1.sale_price if p1.sale_price else p1.price)
        price_b = to_decimal(p2.sale_price if p2.sale_price else p2.price)

        if method == 'max_price':
            unit_price = max(price_a, price_b)
        elif method == 'average':
            unit_price = (price_a + price_b) / Decimal(2)
        elif method == 'sum_halved':
            unit_price = (price_a + price_b) / Decimal(2)
        else:
            unit_price = max(price_a, price_b)

        customizations_whole = normalize_customization_list(data.get('customizations_whole') or [])
        customizations_half1 = normalize_customization_list(data.get('customizations_half1') or [])
        customizations_half2 = normalize_customization_list(data.get('customizations_half2') or [])

        extras_total = (
            sum_customizations_price(customizations_whole)
            + sum_customizations_price(customizations_half1)
            + sum_customizations_price(customizations_half2)
        )

        unit_price = unit_price + extras_total

        ids_sorted = sorted([str(p1.id), str(p2.id)], key=int)
        name = f"{p1.name} / {p2.name}"

        images = [get_image_url_from_product(p1), get_image_url_from_product(p2)]
        combination_details = {
            'product_ids': ids_sorted,
            'names': [p1.name, p2.name],
            'images': images,
            'customizations_whole': customizations_whole,
            'customizations_half1': customizations_half1,
            'customizations_half2': customizations_half2,
        }

        key_payload = {
            'type': 'half_half',
            'product_ids': ids_sorted,
            'customizations_whole': customizations_whole,
            'customizations_half1': customizations_half1,
            'customizations_half2': customizations_half2,
            'notes': notes,
        }
        product_key = build_cart_item_key(f'half:{ids_sorted[0]}:{ids_sorted[1]}', key_payload)

        defaults = {
            'name': name,
            'price': unit_price,
            'quantity': quantity,
            'combination_details': combination_details,
        }
        if notes:
            defaults['notes'] = notes

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product_key=product_key,
            defaults=defaults
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.price = unit_price
            update_fields = ['quantity', 'price']
            if notes:
                cart_item.notes = notes
                update_fields.append('notes')
            cart_item.combination_details = combination_details
            update_fields.append('combination_details')
            cart_item.save(update_fields=update_fields)

        product_label = name

    else:
        product_id = data.get('product_id')
        if not product_id:
            return JsonResponse({'success': False, 'error': 'product_id ausente'}, status=400)

        product = get_object_or_404(Product, id=product_id, tenant=request.tenant, is_available=True)

        base_price = to_decimal(product.sale_price if product.sale_price else product.price)
        customizations = normalize_customization_list(data.get('customizations') or [])
        extras_total = sum_customizations_price(customizations)
        unit_price = base_price + extras_total

        combination_details = {}
        if customizations:
            combination_details['customizations'] = customizations

        key_payload = {
            'type': 'single_product',
            'product_id': str(product.id),
            'customizations': customizations,
            'notes': notes,
        }
        product_key = build_cart_item_key(f'product:{product.id}', key_payload)

        defaults = {
            'product': product,
            'name': product.name,
            'price': unit_price,
            'quantity': quantity,
            'product_key': product_key,
            'combination_details': combination_details,
        }
        if notes:
            defaults['notes'] = notes

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product_key=product_key,
            defaults=defaults
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.price = unit_price
            cart_item.combination_details = combination_details
            update_fields = ['quantity', 'price', 'combination_details']
            if notes:
                cart_item.notes = notes
                update_fields.append('notes')
            cart_item.save(update_fields=update_fields)

        product_label = product.name

    total_items = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
    cart_total = sum((item.get_total_price() for item in cart.items.all()), Decimal('0.00'))

    return JsonResponse({
        'success': True,
        'message': f'{product_label} adicionado!',
        'cart_count': int(total_items),
        'cart_total': str(cart_total),
    })


def cart_view(request):
    cart = get_or_create_cart(request)
    items_qs = cart.items.select_related('product').all()
    items = list(items_qs)

    populate_combination_images_for_items(items, tenant=request.tenant, persist=False)

    total = sum((item.get_total_price() for item in items), Decimal('0.00'))
    context = {
        'cart_items': items,
        'total': float(total),
    }
    return render(request, 'checkout/cart.html', context)


@require_POST
def remove_from_cart(request, cart_item_id=None, product_id=None):
    cid = cart_item_id or product_id

    if not cid:
        return JsonResponse({'success': False, 'error': 'cart_item_id ausente'}, status=400)

    cart = get_or_create_cart(request)
    deleted_count, _ = CartItem.objects.filter(cart=cart, id=cid).delete()

    items = cart.items.select_related('product').all()
    total = sum((item.get_total_price() for item in items), Decimal('0.00'))
    total_items = sum(item.quantity for item in items)

    return JsonResponse({
        'success': True,
        'deleted': int(deleted_count),
        'total': f'R$ {total:.2f}'.replace('.', ','),
        'cart_count': int(total_items)
    })


@require_POST
def update_cart_quantity(request, cart_item_id):
    cart = get_or_create_cart(request)
    quantity = 0
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8') or '{}')
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

        items = cart.items.select_related('product').all()
        total = sum((item.get_total_price() for item in items), Decimal('0.00'))
        total_items = sum(item.quantity for item in items)
        return JsonResponse({
            'success': True,
            'total': f'R$ {total:.2f}'.replace('.', ','),
            'cart_count': int(total_items)
        })
    except CartItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item não encontrado'}, status=404)


@transaction.atomic
def checkout_step_one(request):
    cart = get_or_create_cart(request)
    cart_items = cart.items.select_related('product')

    if not cart_items.exists():
        messages.warning(request, "Seu carrinho está vazio.")
        return redirect('stores:menu')

    subtotal = sum(item.get_total_price() for item in cart_items)
    total = subtotal

    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        phone = request.POST.get('phone')
        cep = request.POST.get('cep')
        address = request.POST.get('address')
        number = request.POST.get('number')
        neighborhood = request.POST.get('neighborhood')
        complement = request.POST.get('complement')
        payment_method = request.POST.get('payment_method')

        order = Order.objects.create(
            tenant=request.tenant,
            customer_phone=phone,
            total=total,
        )

        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item.product,
                quantity=item.quantity
            )

        cart.delete()

        messages.success(request, "Pedido realizado com sucesso!")
        return redirect('checkout:order_success')

    context = {
        'cart_items': [
            {
                'id': item.product.id if item.product else None,
                'name': item.name,
                'price': float(item.price),
                'quantity': item.quantity,
                'total_price': float(item.get_total_price())
            }
            for item in cart_items
        ],
        'subtotal': float(subtotal),
        'total': float(total)
    }
    return render(request, 'checkout/checkout.html', context)


def order_success(request):
    return render(request, 'checkout/order_success.html')


@require_POST
def add_half_half(request):
    """
    Adiciona um item meio-a-meio ao Cart (usando os modelos Cart e CartItem),
    esperando JSON com:
    {
      "product_ids": [id1, id2],
      "quantity": 1,
      "notes": "...",
      "customizations_whole": [...],
      "customizations_half1": [...],
      "customizations_half2": [...]
    }
    """
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.content_type == 'application/json' else request.POST
    except Exception:
        payload = request.POST

    if hasattr(payload, 'getlist'):
        product_ids = payload.get('product_ids') or payload.getlist('product_ids[]') or payload.getlist('product_ids')
    else:
        product_ids = payload.get('product_ids') or payload.get('product_ids[]')

    quantity = payload.get('quantity', 1)
    notes = get_notes_from_payload(payload)

    if isinstance(product_ids, str):
        product_ids = [p.strip() for p in product_ids.split(',') if p.strip()]

    try:
        quantity = int(quantity)
        if quantity < 1:
            quantity = 1
    except Exception:
        quantity = 1

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
        rule = CombinationPricingRule.objects.get(tenant=request.tenant, combination_type='half_half')
        method = rule.price_calculation_method
    except CombinationPricingRule.DoesNotExist:
        method = 'max_price'

    price_a = to_decimal(p1.sale_price if p1.sale_price else p1.price)
    price_b = to_decimal(p2.sale_price if p2.sale_price else p2.price)

    if method == 'max_price':
        unit_price = max(price_a, price_b)
    elif method in ('average', 'sum_halved'):
        unit_price = (price_a + price_b) / Decimal(2)
    else:
        unit_price = max(price_a, price_b)

    customizations_whole = normalize_customization_list(payload.get('customizations_whole') or [])
    customizations_half1 = normalize_customization_list(payload.get('customizations_half1') or [])
    customizations_half2 = normalize_customization_list(payload.get('customizations_half2') or [])

    extras_total = (
        sum_customizations_price(customizations_whole)
        + sum_customizations_price(customizations_half1)
        + sum_customizations_price(customizations_half2)
    )
    unit_price = unit_price + extras_total

    ids_sorted = sorted([str(p1.id), str(p2.id)], key=int)

    key_payload = {
        'type': 'half_half',
        'product_ids': ids_sorted,
        'customizations_whole': customizations_whole,
        'customizations_half1': customizations_half1,
        'customizations_half2': customizations_half2,
        'notes': notes,
    }
    product_key = build_cart_item_key(f'half:{ids_sorted[0]}:{ids_sorted[1]}', key_payload)

    name = f"{p1.name} / {p2.name} (Meio a meio)"
    images = [get_image_url_from_product(p1), get_image_url_from_product(p2)]
    combination_details = {
        'product_ids': ids_sorted,
        'names': [p1.name, p2.name],
        'images': images,
        'customizations_whole': customizations_whole,
        'customizations_half1': customizations_half1,
        'customizations_half2': customizations_half2,
    }

    cart = get_or_create_cart(request)

    defaults = {
        'name': name,
        'price': unit_price,
        'quantity': quantity,
        'combination_details': combination_details,
        'product_key': product_key,
    }
    if notes:
        defaults['notes'] = notes

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product_key=product_key,
        defaults=defaults
    )
    if not created:
        cart_item.quantity = cart_item.quantity + quantity
        cart_item.price = unit_price
        cart_item.combination_details = combination_details
        update_fields = ['quantity', 'price', 'combination_details']
        if notes:
            cart_item.notes = notes
            update_fields.append('notes')
        cart_item.save(update_fields=update_fields)

    total_items = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
    cart_total = sum((item.price * item.quantity) for item in cart.items.all())

    msg = (
        f"Pizza meio a meio adicionada. Será cobrado {format_currency(unit_price)} "
        f"por unidade."
    )

    return JsonResponse({
        'success': True,
        'added': True,
        'message': msg,
        'cart_count': int(total_items),
        'cart_total': str(cart_total),
    })


def format_currency(value: Decimal):
    q = value.quantize(Decimal('0.01'))
    s = f"{q:.2f}"
    return "R$ " + s.replace('.', ',')