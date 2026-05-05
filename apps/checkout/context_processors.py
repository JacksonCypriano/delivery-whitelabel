from django.db import models
from .views import get_or_create_cart

def cart_count(request):
    if hasattr(request, 'tenant'):
        try:
            cart = get_or_create_cart(request)
            count = cart.items.aggregate(total=models.Sum('quantity'))['total'] or 0
            return {'cart_count_global': count}
        except:
            return {'cart_count_global': 0}
    return {'cart_count_global': 0}
