"""Platform counters, with explicit dates and no estimated financial revenue."""
from django.db.models import Count, Sum, Q
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.billing.models import Invoice, Subscription
from apps.orders.models import Order
from apps.prospecting.commercial_models import CommercialConversation


def platform_metrics():
    today=timezone.localdate()
    stores=Tenant.objects.aggregate(total=Count('pk'),active=Count('pk',filter=Q(is_active=True)))
    subscriptions=Subscription.objects.aggregate(managed=Count('pk',filter=Q(managed=True)),suspended=Count('pk',filter=Q(billing_suspended=True)))
    paid=Invoice.objects.filter(environment='production',status='PAID',paid_at__date__gte=today.replace(day=1),paid_at__date__lte=today).aggregate(total=Sum('amount'))['total'] or 0
    return {'date':today.isoformat(),'stores':stores,'subscriptions':subscriptions,'received_month':str(paid),
        'orders_today':list(Order.objects.filter(created_at__date=today,abandoned_at__isnull=True).values('source').annotate(count=Count('pk'))),
        'human_requests':CommercialConversation.objects.filter(paused=True,opted_out=False).exclude(stage__in=['converted','lost']).count()}
