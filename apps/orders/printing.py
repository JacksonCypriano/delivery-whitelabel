"""Snapshot-based non-fiscal thermal receipts and an at-most-once spool queue."""
import re
import textwrap
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from celery import shared_task
from django.db import transaction
from django.db.models import Q, Exists, OuterRef
from django.utils import timezone
from apps.merchant.orders import _payment_info, _base_queryset
from apps.integrations.models import WhatsAppCheckout
from .printing_models import PrintDevice, PrintJob

TEMPLATES={'kitchen':'COZINHA','courier':'ENTREGA','full':'COMPLETA'}


def _safe(text):
    # Never allow user text to become ESC/POS control sequences.
    return ''.join(c for c in str(text or '') if c=='\n' or ord(c)>=32).replace('\x7f','')


def ticket(order,template,width):
    if template not in TEMPLATES or width not in {58,80}: raise ValueError('Formato inválido.')
    if template=='courier' and order.delivery_type!='delivery': raise ValueError('Via de entrega disponível apenas para entrega.')
    lines=[order.tenant.name, f'PEDIDO #{order.pk} · {TEMPLATES[template]}',order.get_source_display(),order.delivery_type_label,timezone.localtime(order.created_at).strftime('%d/%m/%Y %H:%M')]
    external=getattr(order,'external_order',None)
    if external: lines.append('Referência: '+str(external.external_id))
    if template!='kitchen':
        lines.extend([order.customer_name,order.customer_phone])
        if order.delivery_type=='delivery':
            lines.extend([order.delivery_address_label,order.delivery_complement,order.delivery_zip_code,order.delivery_reference])
    lines.append('-'*24)
    def details(data):
        if isinstance(data,dict):
            # Only display known human labels, never raw metadata or identifiers.
            label=data.get('option_name') or data.get('name') or data.get('label')
            if label: lines.append('  '+str(label))
            for v in data.values():
                if isinstance(v,(dict,list)): details(v)
        elif isinstance(data,list):
            for v in data: details(v)
    for item in order.items.all():
        lines.append(f'{item.quantity}x {item.name}')
        details(item.combination_details)
        if item.notes: lines.append('OBS: '+item.notes)
        if template=='full': lines.append(f'  R$ {item.price} / un · R$ {item.get_total_price()}')
    if template!='kitchen':
        checkout=WhatsAppCheckout.objects.filter(order=order).first()
        payment=_payment_info(order,checkout)
        lines.extend(['-'*24,f'Subtotal: R$ {order.subtotal}',f'Entrega: R$ {order.delivery_fee}',f'Desconto: R$ {order.discount_amount}',f'TOTAL: R$ {order.total}',order.payment_label,payment['label']])
        if payment['paid']: lines.append('PAGO · não cobrar novamente')
        elif order.payment_flow in {'in_person','marketplace_due'}: lines.append(f'A cobrar: R$ {order.total}')
        else: lines.append('PAGAMENTO NÃO CONFIRMADO · conferir antes de cobrar')
        if not payment['paid'] and order.payment_method=='cash' and order.payment_change_for:
            try:
                amount=Decimal(order.payment_change_for.replace(',','.'))
                if amount.is_finite() and amount>=order.total:
                    lines.extend([f'Troco solicitado para: R$ {amount:.2f}',f'Troco: R$ {amount-order.total:.2f}', 'Valor informado não comprova recebimento.'])
            except InvalidOperation: pass
    lines.extend(['-'*24,'COMPROVANTE NÃO FISCAL'])
    columns=32 if width==58 else 48
    return '\n'.join(part for line in lines if line for part in textwrap.wrap(_safe(line),columns,replace_whitespace=True))+'\n'


@transaction.atomic
def enqueue(device,order,template,key,original=None):
    if not device.active: raise ValueError('Conecte um dispositivo antes de imprimir.')
    if order.tenant_id!=device.tenant_id: raise ValueError('Pedido de outra loja.')
    if original and (original.device_id!=device.pk or original.order_id!=order.pk): raise ValueError('Via original inválida.')
    text = ('REIMPRESSÃO\n'+original.text if original else ticket(order,template,device.paper_mm))
    job,_=PrintJob.objects.get_or_create(device=device,order=order,template=template,event_key=key,defaults={
        'text':text,'paper_mm':original.paper_mm if original else device.paper_mm,'copies':device.copies,'reprint_of':original})
    return job


@shared_task
def plan_thermal_jobs():
    for device in PrintDevice.objects.filter(active=True,auto_enabled=True):
        cutoff=timezone.now()-timedelta(days=1)
        # An event remains eligible even if the kitchen advanced before Beat ran.
        rows=_base_queryset(device.tenant).filter(
            Q(status=device.trigger,status_updated_at__gte=cutoff) |
            Q(status_events__to_status=device.trigger,status_events__created_at__gte=cutoff)
        ).exclude(status='cancelled').distinct()
        missing=Q(pk__in=[])
        for index,template in enumerate(device.templates):
            key=f'printed_{index}'
            rows=rows.annotate(**{key:Exists(PrintJob.objects.filter(device=device,order_id=OuterRef('pk'),template=template,event_key='auto:'+device.trigger))})
            condition=Q(**{key:False})
            if template=='courier': condition &= Q(delivery_type='delivery')
            missing |= condition
        for order in rows.filter(missing).order_by('pk')[:300]:
            for template in device.templates:
                if template=='courier' and order.delivery_type!='delivery': continue
                enqueue(device,order,template,'auto:'+device.trigger)
