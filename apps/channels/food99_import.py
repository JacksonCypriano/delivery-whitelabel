"""Controlled 99Food sandbox import. No webhooks or outgoing status transitions.

The imported external order is always marked with a warning until official status
and currency mappings are verified. The caller must explicitly acknowledge both.
"""
import json
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.billing.secrets import encrypt_secret
from apps.orders.models import Order, OrderItem
from .connectors import ProviderError
from .food99_mapping_probe import inspect_order
from .models import Connection, ExternalOrder


def minor(value):
    if type(value) is not int or value < 0 or value > 9999999999:
        raise ProviderError('Valor monetário da 99Food inválido.')
    return Decimal(value) / Decimal(100)


def _options(rows, depth=0):
    if depth > 8 or not isinstance(rows, list) or len(rows) > 150:
        raise ProviderError('Adicionais da 99Food excedem limite seguro.')
    options=[]
    for item in rows:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            raise ProviderError('Adicional 99Food inválido.')
        qty=item.get('amount',1)
        if type(qty) is not int or not 1 <= qty <= 100:
            raise ProviderError('Quantidade de adicional 99Food inválida.')
        options.append({'option_name':f'{qty}× {item["name"][:150]}', 'price':str(minor(item.get('total_price',0)))})
        options.extend(_options(item.get('sub_item_list') or [], depth+1))
    return options


def fingerprint_preview(data):
    """Non-PII stable financial/item signature for reviewing repeat imports."""
    import hashlib
    signature = {
        'shop_id': data['shop_id'], 'order_id': data['order_id'],
        'status_code': data['status_code'], 'total': str(data['total']),
        'real_pay': str(data['real_pay']), 'delivery_fee': str(data['delivery_fee']),
        'discount': str(data['discount']),
        'items': [
            {'code': item['code'], 'quantity': item['quantity'],
             'line_total': str(item['line_total']), 'options': item['options']}
            for item in data['items']
        ],
    }
    return hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def preview(detail, *, app_shop_id, shop_id, order_id):
    info=inspect_order(detail,app_shop_id=app_shop_id,shop_id=shop_id,order_id=order_id)
    if info['fields_missing']:
        raise ProviderError('Campos obrigatórios ausentes no pedido 99Food.')
    status=detail['status']
    if type(status) is not int:
        raise ProviderError('Status 99Food inválido.')
    delivery=detail['delivery_type']; pay=detail['pay_type']
    if delivery not in (1,2) or pay not in (1,2,3,4):
        raise ProviderError('Entrega/pagamento 99Food sem mapeamento.')
    p=detail['price']
    total=minor(p['order_price'])
    real=minor(p['real_pay_price'])
    delivery_fee=minor(p.get('delivery_price',0))
    discount=minor(p.get('items_discount',0))+minor(p.get('delivery_discount',0))
    # Until the provider's field semantics are signed off, reject sums that
    # would produce a negative merchant subtotal or impossible charges.
    subtotal = total - delivery_fee + discount
    if subtotal < 0 or real > Decimal('99999999.99'):
        raise ProviderError('Composição financeira da 99Food inválida.')
    if p.get('real_price') is not None:
        minor(p['real_price'])
    if p.get('sku_price') is not None:
        minor(p['sku_price'])

    rows=[]
    for item in detail['order_items']:
        if not isinstance(item,dict) or not isinstance(item.get('name'),str) or not item['name'].strip():
            raise ProviderError('Item 99Food inválido.')
        qty=item.get('amount')
        if type(qty) is not int or not 1 <= qty <= 1000:
            raise ProviderError('Quantidade 99Food inválida.')
        line=minor(item['total_price'])
        # The API may return a line whose division by quantity has subcent
        # precision. Persist line_total explicitly and never silently round
        # the unit price up or down as though it were exact.
        unit=(line/qty).quantize(Decimal('.01'))
        if item.get('sku_price') is not None:
            minor(item['sku_price'])
        rows.append({'name':item['name'][:255], 'quantity':qty, 'price':unit,
                     'line_total':line, 'code':str(item.get('app_item_id') or '')[:100],
                     'notes':str(item.get('remark') or '')[:2000],
                     'options':_options(item.get('sub_item_list') or [])})
    if not rows or len(rows)>200:
        raise ProviderError('Número de itens 99Food inválido.')
    # The provider can include fees/discounts and nested item pricing, so
    # line totals are informative; do not force an unverified equality.
    if sum((row['line_total'] for row in rows), Decimal('0')) > Decimal('99999999.99'):
        raise ProviderError('Total dos itens 99Food excede limite seguro.')
    created=detail.get('create_time')
    if type(created) is not int or not 1000000000 <= created <= 9999999999:
        raise ProviderError('Data de criação 99Food inválida.')
    try:
        created_at=datetime.fromtimestamp(created, tz=dt_timezone.utc)
    except (ValueError,OverflowError,OSError):
        raise ProviderError('Data de criação 99Food inválida.') from None
    return {'order_id':str(order_id),'shop_id':str(shop_id),'status_code':status,
            'delivery_by':'PLATFORM' if delivery==1 else 'MERCHANT',
            'payment_method':{1:'online',2:'cash',3:'pos',4:'wallet'}[pay],
            'paid':pay in (1,4), 'total':total,'real_pay':real,
            'delivery_fee':delivery_fee,'discount':discount,'items':rows,
            'created_at':created_at, 'currency_confirmed':False}


@transaction.atomic
def import_reviewed(detail, *, tenant_id, app_shop_id, shop_id, order_id, currency, status_override):
    """Sandbox-only manual import. Never infer numeric 99Food status meanings."""
    if not getattr(settings,'FOOD99_SANDBOX_ENABLED',False):
        raise ProviderError('99Food sandbox desabilitado.')
    if currency!='BRL' or status_override!='pending':
        raise ProviderError('Importação requer revisão explícita da moeda BRL e estado provisório.')
    data=preview(detail,app_shop_id=app_shop_id,shop_id=shop_id,order_id=order_id)
    from apps.tenants.models import Tenant
    tenant=Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        raise ProviderError('Tenant de destino não encontrado.')
    # Sandbox AppShopID must be bound to the intended tenant, never accepted
    # solely on the basis of a user-provided tenant primary key.
    expected_app_shop_id = 'vdd-' + tenant.slug
    if app_shop_id != expected_app_shop_id:
        raise ProviderError('AppShopID 99Food não corresponde ao tenant selecionado.')
    if getattr(settings, 'FOOD99_SANDBOX_IMPORT_TO_ORDERS', False) is not True:
        raise ProviderError('Importação em Order desabilitada: revisão operacional pendente.')
    conn=Connection.objects.select_for_update().filter(provider='99food',mode='test',merchant_id=str(shop_id)).first()
    if conn and conn.tenant_id!=tenant.pk:
        raise ProviderError('Estabelecimento 99Food associado a outro tenant.')
    if not conn:
        conn=Connection.objects.create(tenant=tenant,provider='99food',mode='test',merchant_id=str(shop_id),merchant_name='99Food Sandbox',enabled=False,status='awaiting_review')
    existing=ExternalOrder.objects.select_for_update().filter(connection=conn,external_id=str(order_id)).first()
    if existing:
        if existing.order.tenant_id != tenant.pk:
            raise ProviderError('Pedido externo associado a outro tenant.')
        if existing.order.source != '99food' or existing.order.tenant_id != tenant.pk:
            raise ProviderError('Pedido previamente importado não corresponde à loja 99Food.')
        # A repeated import must never overwrite the original or apply a stale
        # provider status. Differences are left for explicit reconciliation.
        return existing.order_id,False
    order=Order.objects.create(tenant=tenant,source='99food',status='pending',
       customer_name='Cliente 99Food',total=data['total'],subtotal=data['total']-data['delivery_fee']+data['discount'],
       delivery_fee=data['delivery_fee'],discount_amount=data['discount'],
       delivery_type='delivery',payment_flow='marketplace' if data['paid'] else 'marketplace_due',
       payment_method=data['payment_method'])
    Order.objects.filter(pk=order.pk).update(created_at=data['created_at'])
    for item in data['items']:
        OrderItem.objects.create(order=order,name=item['name'],quantity=item['quantity'],price=item['price'],
          product_key=item['code'],notes=item['notes'],combination_details={
            'external_line_total':str(item['line_total']), 'customizations':item['options']})
    x=ExternalOrder.objects.create(connection=conn,order=order,external_id=str(order_id),
       delivery_by=data['delivery_by'],paid=data['paid'],payment_summary=data['payment_method'],
       financials={'currency':'BRL','total':str(data['total']),'real_pay':str(data['real_pay']),
                   'status_code':data['status_code'], 'snapshot_fingerprint':fingerprint_preview(data)},
       encrypted_snapshot=encrypt_secret(json.dumps({'provider':detail},default=str)),
       warning='SANDBOX: status 99Food não homologado; não executar transições ou expedir pedido.')
    return x.order_id,True
