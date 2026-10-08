from urllib.parse import urlencode
from .storefront import address_payload


def marketplace_props(request, c):
    def page_url(page):
        if page is None:
            return None
        query = request.GET.copy()
        query['page'] = page
        return '?' + query.urlencode()
    page = c['page_obj']
    return {
        **{k: c[k] for k in ('search', 'selected_city', 'selected_state', 'selected_category', 'open_only', 'favorites_only', 'favorite_count', 'result_count', 'location_active', 'global_delivery_location', 'cities')},
        'customer_addresses': [address_payload(a) for a in c['customer_addresses']],
        'categories': list(c['categories'].values('name', 'slug', 'icon')),
        'stores': [{
            'id': s['tenant'].pk, 'name': s['tenant'].name, 'description': s['profile'].short_description,
            'city': s['profile'].city, 'state': s['profile'].state,
            **{k: s[k] for k in ('is_open', 'logo_url', 'url', 'distance_km', 'delivery', 'is_favorite')},
            'categories': [{'name': c.name, 'icon': c.icon} for c in s['categories']],
            'matched_products': [{'id': p.pk, 'name': p.name, 'price': str(p.effective_price)} for p in s['matched_products']],
        } for s in c['stores']],
        'pagination': {'page': page.number, 'previous': page_url(page.previous_page_number()) if page.has_previous() else None,
                       'next': page_url(page.next_page_number()) if page.has_next() else None},
    }
