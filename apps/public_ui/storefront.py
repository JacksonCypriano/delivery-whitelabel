"""Public DTOs are allowlists: no payment credentials, OTPs or tenant secrets."""
from django.utils import timezone
from apps.orders.cart_service import product_price
from apps.tenants.context_processors import tenant_brand


def address_payload(a):
    return {key: getattr(a, key) for key in ('id', 'label', 'street', 'number', 'complement', 'neighborhood', 'city', 'state', 'zip_code', 'reference', 'is_default')}


def store_payload(request):
    tenant = getattr(request, 'tenant', None)
    if not tenant: return None
    from apps.checkout.views import get_pickup_address
    brand = getattr(tenant, 'brand_config', None)
    fields = ('primary_color', 'secondary_color', 'accent_color', 'background_color', 'card_background_color', 'text_color', 'muted_text_color', 'border_color', 'button_text_color', 'font_family', 'border_radius', 'button_radius', 'base_font_size', 'show_search_bar', 'show_category_icons', 'show_product_description', 'show_product_image', 'compact_product_cards', 'card_shadow', 'hover_effect', 'header_style', 'dark_mode_enabled', 'dark_mode_primary', 'dark_mode_background', 'dark_mode_card_background', 'dark_mode_text', 'dark_mode_muted_text', 'dark_mode_border_color')
    def image(name):
        file = getattr(brand, name, None)
        return file.url if file else ''
    return {'name': tenant.name, 'slug': tenant.slug, 'accepts_delivery': tenant.accepts_delivery,
            'accepts_pickup': tenant.accepts_pickup, 'pickup_address': get_pickup_address(tenant),
            'whatsapp': tenant.whatsapp_number, 'is_open': tenant.is_open_now(),
            'brand': {key: getattr(brand, key, None) for key in fields},
            'hours': [{'day': h.get_weekday_display(), 'closed': h.is_closed, 'open': h.opening_time.strftime('%H:%M') if h.opening_time else '', 'close': h.closing_time.strftime('%H:%M') if h.closing_time else ''} for h in tenant.business_hours.all().order_by('weekday', 'opening_time')],
            'favicon': image('favicon'), 'logo': image('logo'), 'banner': image('banner'), 'cart_count': tenant_brand(request)['cart_count_global']}


def catalog_payload(request, c):
    half_ids = {row.product_id for row in c['half_products']}
    categories = []
    for category in c['categories']:
        products = []
        for p in category.prefetched_products:
            products.append({'id': p.pk, 'name': p.name, 'slug': p.slug, 'description': p.description,
                'price': str(product_price(p)), 'original_price': str(p.price), 'sale_price': str(p.sale_price) if p.sale_price is not None else None,
                'image': p.get_primary_image() or '', 'category_id': category.pk,
                'images': [i.image.url for i in p.images.all() if i.image],
                'min_qty': p.min_order_qty, 'max_qty': p.max_order_qty or 99,
                'available': p.stock is None or p.stock > 0, 'half_enabled': p.pk in half_ids,
                'is_featured': p.is_featured, 'is_vegan': p.is_vegan, 'is_spicy': p.is_spicy,
                'allergens': p.allergens, 'calories': p.calories, 'weight': str(p.weight) if p.weight else '', 'prep_time': p.prep_time})
        categories.append({'id': category.pk, 'name': category.name, 'products': products})
    return {'categories': categories, 'delivery_zones': c['delivery_zones'], 'open_product_slug': c.get('open_product_slug'), 'deep_link_unavailable': c.get('deep_link_unavailable')}


def cart_item_payload(item):
    return {'id': item.pk, 'name': item.name, 'quantity': item.quantity, 'price': str(item.price), 'total': str(item.get_total_price()),
            'notes': item.notes, 'combination_details': item.combination_details or {},
            'image': item.product.get_primary_image() if item.product else '',
            'min_qty': item.product.min_order_qty if item.product else 1,
            'max_qty': (item.product.max_order_qty or 99) if item.product else 99}


def commerce_props(request, page, c):
    from .rendering import order_payload
    if page == 'catalog': return catalog_payload(request, c)
    if page == 'cart':
        return {'items': [cart_item_payload(i) for i in c['cart_items']], 'subtotal': c['subtotal'],
                'total': c['total'], 'delivery_fee': c['delivery_fee'], 'delivery_fee_display': c['delivery_fee_display'],
                'can_checkout': c['cart_can_checkout'], 'delivery_available': c['delivery_available'],
                'checkout_mode_hint': c['cart_checkout_mode_hint'], 'location': c['global_delivery_location']}
    if page == 'checkout':
        from apps.orders.models import SalesSettings
        cfg = SalesSettings.objects.filter(tenant=request.tenant).first()
        return {'scheduling_enabled': bool(cfg and cfg.scheduling_enabled), **{key: c.get(key) for key in ('cart_items', 'subtotal', 'total', 'delivery_zones', 'store_address', 'global_delivery_location', 'use_global_manual_address', 'initial_full_name', 'initial_phone', 'checkout_token', 'online_payment_available')},
                'customer_addresses': [address_payload(a) for a in c['customer_addresses']],
                'default_address': address_payload(c['default_address']) if c.get('default_address') else None}
    if page in {'review','payment'}:
        p = c.get('payment') or getattr(c['order'], 'online_payment', None)
        order = c['order']
        return {'order': order_payload(order), 'online_payment_available': c.get('online_payment_available', False),
                'payment': {'status': p.status, 'label': p.get_status_display(), 'checkout_url': p.checkout_url,
                            'confirmation_code': p.confirmation_code if p.status == 'PAID' else ''} if p else None}
    return {'message': 'Pedido registrado. Acompanhe a confirmação da loja.'}
