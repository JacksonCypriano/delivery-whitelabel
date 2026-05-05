# apps/checkout/views.py
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.stores.models import Product
from apps.orders.models import Cart, CartItem, Order, OrderItem

User = get_user_model()

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

def add_to_cart(request):
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 1))
        product = get_object_or_404(Product, id=product_id, tenant=request.tenant)

        cart = get_or_create_cart(request)
        
        # Atualizar ou criar item
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity, 'tenant': request.tenant}
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        # Calcular total de itens no carrinho
        total_items = cart.items.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0

        return JsonResponse({
            'success': True,
            'message': f'{product.name} adicionado!',
            'cart_count': total_items
        })

@require_POST
def remove_from_cart(request, product_id):
    cart = get_or_create_cart(request)
    CartItem.objects.filter(
        cart=cart, 
        product_id=product_id,
        cart__tenant=request.tenant
    ).delete()
    
    # Recalcular totais
    items = cart.items.select_related('product')
    total = sum(item.get_total_price() for item in items)
    total_items = sum(item.quantity for item in items)
    
    return JsonResponse({
        'success': True,
        'total': f'R$ {total:.2f}'.replace('.', ','),
        'cart_count': total_items
    })

@require_POST
def update_cart_quantity(request, product_id):
    cart = get_or_create_cart(request)
    quantity = int(request.POST.get('quantity', 0))
    
    try:
        cart_item = CartItem.objects.get(
            cart=cart,
            product_id=product_id,
            cart__tenant=request.tenant
        )
        
        if quantity <= 0:
            cart_item.delete()
        else:
            cart_item.quantity = quantity
            cart_item.save()
        
        # Recalcular totais
        items = cart.items.select_related('product')
        total = sum(item.get_total_price() for item in items)
        total_items = sum(item.quantity for item in items)
        
        return JsonResponse({
            'success': True,
            'total': f'R$ {total:.2f}'.replace('.', ','),
            'cart_count': total_items
        })
    except CartItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item não encontrado'})

def cart_view(request):
    cart = get_or_create_cart(request)
    items = cart.items.select_related('product')
    total = sum(item.get_total_price() for item in items)
    
    context = {
        'cart_items': [
            {
                'id': item.product.id,
                'name': item.product.name,
                'price': float(item.product.price),
                'quantity': item.quantity,
                'total_price': float(item.get_total_price())
            }
            for item in items
        ],
        'total': float(total)
    }
    return render(request, 'checkout/cart.html', context)

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
        # Coletar dados do formulário
        full_name = request.POST.get('full_name')
        phone = request.POST.get('phone')
        cep = request.POST.get('cep')
        address = request.POST.get('address')
        number = request.POST.get('number')
        neighborhood = request.POST.get('neighborhood')
        complement = request.POST.get('complement')
        payment_method = request.POST.get('payment_method')

        # Criar o pedido
        order = Order.objects.create(
            tenant=request.tenant,
            customer_phone=phone,
            total=total,
            # Você pode adicionar mais campos aqui conforme necessário
        )

        # Criar itens do pedido
        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item.product,
                quantity=item.quantity
            )

        # APENAS AGORA apagar o carrinho após criar o pedido
        cart.delete()

        messages.success(request, "Pedido realizado com sucesso!")
        return redirect('checkout:order_success')

    # Para requisições GET, mostrar o formulário
    context = {
        'cart_items': [
            {
                'id': item.product.id,
                'name': item.product.name,
                'price': float(item.product.price),
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