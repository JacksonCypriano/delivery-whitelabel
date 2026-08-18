from django.db.models import Count
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Order


@api_view(['GET'])
def order_report(request):
    """Resumo simples de pedidos por status para a loja atual (request.tenant).

    As vendas são finalizadas via WhatsApp (sem gateway de pagamento externo).
    Este endpoint apenas retorna a contagem de pedidos por status.
    """
    tenant = getattr(request, 'tenant', None)
    orders = (
        Order.objects
        .filter(tenant=tenant)
        .values('status')
        .annotate(total=Count('id'))
    )
    return Response({'orders_by_status': list(orders)})
