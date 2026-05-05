# apps/checkout/views.py
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.stores.models import Product


def add_to_cart(request):
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 1))
        product = get_object_or_404(Product, id=product_id)

        cart = request.session.get('cart', {})

        key = f"product_{product.id}"
        if key in cart:
            cart[key]['quantity'] += quantity
        else:
            cart[key] = {
                'id': product.id,
                'name': product.name,
                'price': float(product.price),
                'quantity': quantity,
            }

        request.session['cart'] = cart
        request.session.modified = True

        # Contagem total de itens no carrinho
        total_items = sum(item['quantity'] for item in cart.values())

        return JsonResponse({
            'success': True,
            'message': f'{product.name} adicionado!',
            'cart_count': total_items
        })

def cart_view(request):
    cart = request.session.get('cart', {})
    items = list(cart.values())
    total = sum(item['price'] * item['quantity'] for item in items)
    return render(request, 'checkout/cart.html', {
        'cart_items': items,
        'total': total
    })

def checkout_step_one(request):
    cart = request.session.get('cart', {})
    items = list(cart.values())
    
    if not items:
        messages.warning(request, "Seu carrinho está vazio.")
        return redirect('stores:menu')  # redireciona se não tiver nada no carrinho

    subtotal = sum(float(item['price']) * item['quantity'] for item in items)
    total = subtotal  # taxa grátis (pode mudar depois)

    if request.method == 'POST':
        # Captura dados do formulário
        full_name = request.POST.get('full_name')
        phone = request.POST.get('phone')
        cep = request.POST.get('cep')
        address = request.POST.get('address')
        number = request.POST.get('number')
        neighborhood = request.POST.get('neighborhood')
        complement = request.POST.get('complement')
        payment_method = request.POST.get('payment_method')

        # TODO: Salvar os dados em uma Order ou processar pagamento
        
        # Limpa o carrinho após finalizar
        request.session['cart'] = {}
        request.session.modified = True

        messages.success(request, "Pedido realizado com sucesso!")
        return redirect('checkout:order_success')  # página de sucesso

    return render(request, 'checkout/checkout.html', {
        'cart_items': items,
        'subtotal': subtotal,
        'total': total
    })


def order_success(request):
    return render(request, 'checkout/order_success.html')