from apps.orders.models import Cart, CartItem
from django.db.models import Sum

def tenant_brand(request):
    cart_count = 0
    try:
        if request.user.is_authenticated:
            cart = Cart.objects.filter(tenant=request.tenant, user=request.user).first()
        else:
            session_key = request.session.session_key
            cart = Cart.objects.filter(tenant=request.tenant, session_key=session_key).first() if session_key else None

        if cart:
            cart_count = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
    except Exception:
        pass

    return {
        'tenant': getattr(request, 'tenant', None),
        'tenant_brand': getattr(request.tenant, 'brandconfig', None) if getattr(request, 'tenant', None) else None,
        'cart_count_global': int(cart_count),
    }