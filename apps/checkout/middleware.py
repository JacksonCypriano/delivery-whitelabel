# apps/checkout/middleware.py
from apps.orders.models import Cart

class CartMergeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (request.user.is_authenticated and 
            hasattr(request, 'session') and 
            request.session.session_key):
            
            try:
                anon_cart = Cart.objects.get(
                    session_key=request.session.session_key,
                    user__isnull=True,
                    tenant=request.tenant
                )
                
                user_cart, created = Cart.objects.get_or_create(
                    user=request.user,
                    tenant=request.tenant
                )
                
                for anon_item in anon_cart.items.all():
                    user_item, item_created = user_cart.items.get_or_create(
                        product=anon_item.product,
                        defaults={
                            'quantity': anon_item.quantity,
                            'tenant': request.tenant
                        }
                    )
                    if not item_created:
                        user_item.quantity += anon_item.quantity
                        user_item.save()
                
                anon_cart.delete()
                
            except Cart.DoesNotExist:
                pass
        
        response = self.get_response(request)
        return response
