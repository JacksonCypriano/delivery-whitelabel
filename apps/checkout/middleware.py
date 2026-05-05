# apps/checkout/middleware.py
from .models import Cart

class CartMergeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Após login, verificar se precisa mesclar carrinhos
        if (request.user.is_authenticated and 
            hasattr(request, 'session') and 
            request.session.session_key):
            
            try:
                # Carrinho anônimo
                anon_cart = Cart.objects.get(
                    session_key=request.session.session_key,
                    user__isnull=True,
                    tenant=request.tenant
                )
                
                # Carrinho do usuário logado
                user_cart, created = Cart.objects.get_or_create(
                    user=request.user,
                    tenant=request.tenant
                )
                
                # Mesclar itens
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
                
                # Apagar carrinho anônimo
                anon_cart.delete()
                
            except Cart.DoesNotExist:
                pass  # Não há carrinho anônimo para mesclar
        
        response = self.get_response(request)
        return response