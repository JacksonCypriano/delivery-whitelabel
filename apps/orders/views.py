import stripe
from django.conf import settings
from django.db.models import Count
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Order

stripe.api_key = settings.STRIPE_SECRET_KEY

@api_view(['GET'])
def order_report(request):
    tenant = getattr(request, 'tenant', None)
    orders = Order.objects.filter(tenant=tenant).values('status').annotate(total=Count('id'))
    return Response({'orders_by_status': list(orders)})

@api_view(['POST'])
def create_checkout_session(request):
    tenant = getattr(request, 'tenant', None)
    line_items = [{
        'price_data': {
            'currency': 'brl',
            'product_data': {
                'name': 'Pedido',
            },
            'unit_amount': 5000,  # R$50,00
        },
        'quantity': 1,
    }]

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        success_url='https://seudominio.com/success',
        cancel_url='https://seudominio.com/cancel',
    )
    return Response({'url': session.url})