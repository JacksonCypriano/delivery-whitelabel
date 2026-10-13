"""Strict supported Food snapshot. Never reprice external orders locally."""
from decimal import Decimal, InvalidOperation
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from .connectors import ProviderError

def timestamp(value):
    dt=parse_datetime(str(value or ''))
    if not dt or timezone.is_naive(dt): raise ProviderError('Data externa ausente ou sem fuso horário.')
    return dt

def money(value):
    try:
        d=Decimal(str(value))
        if not d.is_finite() or d<0 or d>Decimal('99999999.99'):raise ValueError
        return d.quantize(Decimal('.01'))
    except (ValueError,InvalidOperation):raise ProviderError('Valor monetário externo inválido.') from None

def normalize_ifood(data):
    try:
        if data['orderType'] not in ('DELIVERY','TAKEOUT'):raise ProviderError('Modalidade iFood ainda não suportada; pedido retido para análise.')
        if data.get('category','FOOD')!='FOOD':raise ProviderError('Categoria externa ainda não homologada; pedido retido para análise.')
        items=[]
        def options(rows):
            result=[]
            for opt in rows or []:
                result.append({'option_name':f"{opt.get('quantity',1)}× {opt['name']}",'price':str(money(opt.get('unitPrice',0)))})
                result.extend(options(opt.get('options',[])))
                result.extend(options(opt.get('customizations',[])))
            return result
        for i in data['items']:
            qty=Decimal(str(i['quantity']))
            if qty!=int(qty) or qty<=0:raise ProviderError('Quantidade fracionária requer adaptação do catálogo; pedido retido para análise.')
            items.append({'code':str(i.get('externalCode','')),'name':i['name'],'quantity':int(qty),'price':str(money(i['totalPrice'])/qty),'notes':str(i.get('observations','')),'details':{'customizations':options(i.get('options',[])),'external_line_total':str(money(i['totalPrice']))}})
        if not items:raise ProviderError('Pedido externo sem itens.')
        delivery=data.get('delivery',{})
        address=delivery.get('deliveryAddress',{})
        payment=data['payments']
        methods=payment.get('methods',[])
        prepaid=money(payment['prepaid'])
        pending=money(payment['pending'])
        total=data['total']
        schedule=data.get('schedule') or data.get('scheduled') or {}
        scheduled=schedule.get('deliveryDateTimeStart') if data.get('orderTiming')=='SCHEDULED' else None
        if data.get('orderTiming')=='SCHEDULED' and not scheduled:raise ProviderError('Agendamento sem horário; conferir pedido na plataforma.')
        return {'prepare_after':data.get('preparationStartDateTime') or schedule.get('preparationStartDateTime'),'scheduled_until':schedule.get('deliveryDateTimeEnd'),'platform_notes':' · '.join(str(v) for v in [data.get('extraInfo'),delivery.get('observations'),data.get('takeout',{}).get('observations')] if v),'financials':{'prepaid':str(prepaid),'pending':str(pending),'additional_fees':str(money(total.get('additionalFees',0)))},'external_id':str(data['id']),'merchant_id':str(data['merchant']['id']),'display_id':str(data.get('displayId','')),'customer_name':str(data.get('customer',{}).get('name','Cliente marketplace')),'created_at':data['createdAt'],'scheduled_for':scheduled,'delivery_type':'pickup' if data['orderType']=='TAKEOUT' else 'delivery','delivery_by':delivery.get('deliveredBy','UNKNOWN'),'paid':pending==0,'payment_summary':'; '.join(str(m.get('method','')) for m in methods),'total':str(money(total['orderAmount'])),'subtotal':str(money(total['subTotal'])),'delivery_fee':str(money(total.get('deliveryFee',0))),'discount':str(money(total['benefits']) if 'benefits' in total else sum((money(b.get('value',0)) for b in data.get('benefits',[])),Decimal(0))),'items':items,'address':{'delivery_street':address.get('streetName',''),'delivery_number':address.get('streetNumber',''),'delivery_complement':address.get('complement',''),'delivery_neighborhood':address.get('neighborhood',''),'delivery_city':address.get('city',''),'delivery_state':address.get('state',''),'delivery_zip_code':address.get('postalCode',''),'delivery_reference':address.get('reference','')}}
    except (KeyError,TypeError,ValueError,InvalidOperation,AttributeError,RecursionError):
        raise ProviderError('Detalhes iFood incompletos ou incompatíveis; pedido retido para análise.') from None
