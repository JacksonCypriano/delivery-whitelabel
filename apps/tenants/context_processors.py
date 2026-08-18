from django.db.models import Sum

from apps.orders.models import Cart


def tenant_brand(request):
    """Disponibiliza globalmente nos templates:

    - ``tenant``: a loja atual (resolvida pelo subdomínio no middleware).
    - ``tenant_brand``: a configuração de marca (cores/logo) da loja.
    - ``cart_count_global``: total de itens no carrinho, já no primeiro render.
    """
    tenant = getattr(request, "tenant", None)
    brand = getattr(tenant, "brand_config", None) if tenant else None

    cart_count = 0
    try:
        if tenant is not None:
            if request.user.is_authenticated:
                cart = Cart.objects.filter(tenant=tenant, user=request.user).first()
            else:
                session_key = request.session.session_key
                cart = (
                    Cart.objects.filter(tenant=tenant, session_key=session_key).first()
                    if session_key else None
                )
            if cart:
                cart_count = cart.items.aggregate(total=Sum("quantity"))["total"] or 0
    except Exception:
        cart_count = 0

    return {
        "tenant": tenant,
        "tenant_brand": brand,
        "cart_count_global": int(cart_count),
    }
