"""Read official prices. Publication never edits plans, subscriptions or invoices."""
import hashlib
import json
from decimal import Decimal
from apps.billing.models import Plan, AdditionalService, BillingSettings


def catalog():
    plans = list(Plan.objects.filter(active=True).order_by('months'))
    expected = {1: Decimal('0'), 3: Decimal('5'), 6: Decimal('10'), 12: Decimal('15')}
    valid = len(plans) == 4 and all(p.monthly_price == Decimal('149.90') and p.discount == expected.get(p.months) for p in plans)
    policy = BillingSettings.current()
    data = {
        'plans': [{'id':p.pk,'name':p.name,'months':p.months,'monthly_price':str(p.monthly_price),'discount':str(p.discount),'total':str(p.price)} for p in plans],
        'services': list(AdditionalService.objects.filter(active=True).order_by('code').values('code','name','price')),
        'payments': [name for name in ('pix','boleto','card') if getattr(policy,name+'_enabled')],
        'terms': 'Pagamento antecipado pelo período. Sem comissão do VemDeDelivery sobre pedidos diretos; taxas de terceiros são independentes. Serviços adicionais são opcionais. Não oferecer gratuidade, parcelamento ou desconto fora do catálogo.',
    }
    data = json.loads(json.dumps(data, default=str))
    fingerprint = hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    return {'data':data,'fingerprint':fingerprint,'valid':valid}


def published_catalog(control):
    result = catalog()
    if not result['valid'] or result['fingerprint'] != control.catalog_fingerprint:
        raise ValueError('catalog_review_required')
    return result
