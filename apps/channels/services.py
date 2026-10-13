import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.billing.secrets import encrypt_secret, decrypt_secret
from apps.orders.models import Order, OrderItem, OrderStatusEvent
from apps.orders import inventory
from apps.orders.choices import Status
from apps.orders.operations import OrderOperationError
from .models import Connection, ExternalOrder, Inbox, Outbox, ProductLink
from .connectors import connector, ProviderError
from .normalize import normalize_ifood, timestamp, money

STATES={'PLC':'pending','PLACED':'pending','CFM':'confirmed','CONFIRMED':'confirmed','PRS':'preparing','PREPARATION_STARTED':'preparing','RTP':'ready','READY_TO_PICKUP':'ready','DSP':'out_for_delivery','DISPATCHED':'out_for_delivery','CON':'delivered','CONCLUDED':'delivered','CAN':'cancelled','CANCELLED':'cancelled'}
RANK={'pending':0,'confirmed':1,'preparing':2,'ready':3,'ready_for_pickup':3,'out_for_delivery':4,'delivered':5,'cancelled':6}
WAITING=('pending','sending','awaiting','uncertain')

def external(order):
    return getattr(order,'external_order',None)

def permitted(order, ignore_pending=False):
    x=external(order)
    if not x or not x.connection.enabled:return []
    if x.connection.provider=='99food' and x.connection.mode!='simulation':return []
    if not ignore_pending and any(c.state in WAITING for c in x.commands.all()):return []
    if order.status in ('delivered','cancelled'):return []
    if order.status=='pending':return ['confirmed','cancelled']
    if order.status in ('confirmed','preparing') and x.prepare_after and x.prepare_after>timezone.now():return ['cancelled']
    if order.status=='confirmed':return ['preparing','ready_for_pickup' if order.delivery_type=='pickup' else 'ready','cancelled']
    if order.status=='preparing':return ['ready_for_pickup' if order.delivery_type=='pickup' else 'ready','cancelled']
    if order.status=='ready' and x.delivery_by=='MERCHANT' and (not order.scheduled_for or order.scheduled_for<=timezone.now()):return ['out_for_delivery','cancelled']
    if order.status in ('ready','ready_for_pickup'):return ['cancelled']
    return []

def presentation(order):
    x=external(order)
    if not x:return {'channel':'vemdedelivery','channel_label':'VemDeDelivery','external_id':None}
    command=max(x.commands.all(),key=lambda c:(c.created_at,c.pk),default=None)
    return {'channel':x.connection.provider,'channel_label':x.connection.get_provider_display(),'external_id':x.external_id,'external_display_id':x.display_id,'channel_financials':x.financials,'prepare_after':x.prepare_after,'scheduled_until':x.scheduled_until,'platform_notes':x.platform_notes,'channel_test':x.connection.mode!='live','channel_simulated':x.connection.mode=='simulation','delivery_by':x.delivery_by,'channel_warning':x.warning,'sync_state':command.state if command else '', 'sync_error':command.error if command else ''}

@transaction.atomic
def receive(connection, payload):
    conn=Connection.objects.select_for_update().get(pk=connection.pk)
    if not conn.enabled:raise ProviderError('Integração desconectada.')
    if str(payload.get('merchantId',''))!=conn.merchant_id:raise ProviderError('Estabelecimento externo incompatível.')
    for key in ('id','orderId','code'):
        if not isinstance(payload.get(key),str) or not 0<len(payload[key])<=128:raise ProviderError('Evento externo inválido.')
    code=payload.get('fullCode') or payload['code']
    if not isinstance(code,str) or not 0<len(code)<=80:raise ProviderError('Código externo inválido.')
    row,_=Inbox.objects.get_or_create(connection=conn,external_id=payload['id'],defaults={'order_id':payload['orderId'],'code':code,'occurred_at':timestamp(payload.get('createdAt')),'payload':{k:payload.get(k) for k in ('id','orderId','merchantId','code','fullCode','createdAt')}})
    if row.order_id!=payload['orderId']:raise ProviderError('Identificador de evento reutilizado com outro pedido.')
    return row

def _stock(x,order,normalized):
    if x.stock_state!='pending':return
    links={r.external_code:r.product for r in ProductLink.objects.filter(connection=x.connection).select_related('product')}
    lines=[];missing=False
    for item in normalized['items']:
        product=links.get(item['code'])
        if not product:missing=True;continue
        if product.tenant_id!=order.tenant_id:raise ProviderError('Mapeamento de estoque pertence a outra loja.')
        lines.append((SimpleNamespace(products=[product]),item['quantity']))
    try:
        # Savepoint keeps an insufficient-stock error from breaking order import.
        with transaction.atomic():
            if lines:inventory.consume(order,lines)
        x.stock_state='partial' if missing else 'consumed'
        if missing:x.warning='Itens sem vínculo local: estoque não movimentado para esses itens.'
    except ValueError:
        x.stock_state='error';x.warning='Estoque local insuficiente. Pedido externo preservado; confira o estoque.'

@transaction.atomic
def apply_event(event_id, normalized=None, raw=None):
    initial=Inbox.objects.get(pk=event_id)
    conn=Connection.objects.select_for_update().get(pk=initial.connection_id)
    e=Inbox.objects.select_for_update().get(pk=event_id)
    if e.state in ('processed','ignored'):return
    if not conn.enabled:raise ProviderError('Integração desconectada.')
    x=ExternalOrder.objects.select_for_update().filter(connection=conn,external_id=e.order_id).first()
    target=STATES.get(e.code)
    if e.code in ('CANCELLATION_REQUEST_FAILED','CARF'):
        if x:x.commands.filter(target='cancelled',state__in=WAITING).update(state='failed',error='A plataforma recusou o cancelamento.')
        e.state='processed';e.save(update_fields=['state']);return
    if not target:
        e.state='ignored';e.error='Evento sem transição implementada; revisão operacional necessária.';e.save(update_fields=['state','error'])
        if x:
            x.warning='Evento externo não suportado: confira o pedido no portal da plataforma.';x.save(update_fields=['warning'])
        return
    if x and x.last_event_at and e.occurred_at<x.last_event_at:
        e.state='ignored';e.error='Evento anterior ao último estado aplicado.';e.save(update_fields=['state','error']);return
    if not x:
        if normalized is None:
            api=connector(conn)
            raw=api.detail(e.order_id)
            normalized=api.normalize(raw)
        if str(normalized['merchant_id'])!=conn.merchant_id or str(normalized['external_id'])!=e.order_id:
            raise ProviderError('Pedido externo pertence a outro estabelecimento.')
        created=timestamp(normalized['created_at'])
        address = normalized.get('address', {})
        for field, value in address.items():
            if field not in ('delivery_street','delivery_number','delivery_complement','delivery_neighborhood','delivery_city','delivery_state','delivery_zip_code','delivery_reference') or len(str(value)) > Order._meta.get_field(field).max_length:
                raise ProviderError('Endereço externo excede o formato local; confira na plataforma.')
        order=Order.objects.create(tenant=conn.tenant,source=conn.provider,customer_name=normalized['customer_name'][:150],customer_phone='',total=money(normalized['total']),subtotal=money(normalized['subtotal']),delivery_fee=money(normalized['delivery_fee']),discount_amount=money(normalized['discount']),payment_flow='marketplace' if normalized['paid'] else 'marketplace_due',payment_method=normalized['payment_summary'][:30],delivery_type=normalized['delivery_type'],scheduled_for=timestamp(normalized['scheduled_for']) if normalized.get('scheduled_for') else None,**{k:str(v) for k,v in address.items()})
        Order.objects.filter(pk=order.pk).update(created_at=created)
        for item in normalized['items']:
            qty=item['quantity']
            if not isinstance(qty,int) or qty<1:raise ProviderError('Quantidade externa não suportada.')
            OrderItem.objects.create(order=order,name=item['name'][:255],price=money(item['price']),quantity=qty,notes=item.get('notes',''),combination_details=item.get('details',{}),product_key=item.get('code','')[:100])
        x=ExternalOrder.objects.create(connection=conn,order=order,external_id=e.order_id,display_id=normalized['display_id'][:80],delivery_by=normalized['delivery_by'],paid=normalized['paid'],prepare_after=timestamp(normalized['prepare_after']) if normalized.get('prepare_after') else None,scheduled_until=timestamp(normalized['scheduled_until']) if normalized.get('scheduled_until') else None,platform_notes=normalized.get('platform_notes',''),payment_summary=normalized['payment_summary'][:200],financials=normalized.get('financials',{}),encrypted_snapshot=encrypt_secret(json.dumps({'normalized':normalized,'provider':raw},default=str)))
    else:
        order=Order.objects.select_for_update().get(pk=x.order_id)
        normalized=json.loads(decrypt_secret(x.encrypted_snapshot))['normalized']
    if target=='ready' and order.delivery_type=='pickup':target='ready_for_pickup'
    previous=order.status
    # Never regress even if the platform replays a later timestamp with an old state.
    if RANK[target]<RANK[previous] or (previous in ('delivered','cancelled') and target!=previous):
        e.state='ignored';e.error='Regressão ou conflito com estado terminal; conferir na plataforma.'
        x.warning=e.error;x.save(update_fields=['warning']);e.save(update_fields=['state','error']);return
    if target=='cancelled':
        inventory._cancel_locked(order.pk,order.tenant,external_event=True)
        x.stock_state='returned';order.refresh_from_db()
    else:
        if target!='pending':_stock(x,order,normalized)
        order.status=target;order.status_updated_at=e.occurred_at
        if target in ('confirmed','preparing') and not order.estimated_ready_at:
            from apps.orders.models import OrderNotificationSettings
            cfg,_=OrderNotificationSettings.objects.get_or_create(tenant=order.tenant)
            order.estimated_ready_at=order.scheduled_for or e.occurred_at+timedelta(minutes=cfg.default_prep_minutes)
        order.save(update_fields=['status','status_updated_at','estimated_ready_at'])
    x.last_event_at=e.occurred_at;x.save(update_fields=['last_event_at','stock_state','warning'])
    OrderStatusEvent.objects.create(order=order,tenant=order.tenant,from_status=previous,to_status=target,source='system',note='Evento '+conn.get_provider_display(),metadata={'external_event':e.external_id,'send_notification':False})
    x.commands.filter(target=target,state__in=WAITING).update(state='confirmed',error='')
    # Superseded requests are no longer eligible for retransmission.
    remaining=x.commands.filter(state__in=WAITING).exclude(target=target)
    if target not in ('delivered','cancelled'):
        remaining=remaining.filter(target__in=[s for s,v in RANK.items() if v<RANK[target]])
    remaining.update(state='superseded')
    e.state='processed';e.error='';e.save(update_fields=['state','error'])
    conn.last_sync=timezone.now();conn.last_error='';conn.status='connected';conn.save(update_fields=['last_sync','last_error','status'])

@transaction.atomic
def queue_transition(order_id,tenant,target,actor=None,payload=None):
    # Same lock order as incoming events: connection -> external order -> order.
    x=ExternalOrder.objects.select_related('connection').get(order_id=order_id,order__tenant=tenant)
    conn=Connection.objects.select_for_update().get(pk=x.connection_id)
    x=ExternalOrder.objects.select_for_update().select_related('connection').get(pk=x.pk)
    order=Order.objects.select_for_update().get(pk=order_id,tenant=tenant)
    if target==order.status:return order,None
    if target not in permitted(order):raise OrderOperationError('Ação não permitida ou aguardando confirmação da plataforma.')
    if not conn.enabled:raise OrderOperationError('Integração desconectada.')
    payload=payload or {}
    if target=='cancelled' and (not isinstance(payload.get('cancellationCode'),str) or not isinstance(payload.get('reason'),str) or not 0<len(payload['cancellationCode'])<=20 or not 0<len(payload['reason'].strip())<=500):
        raise OrderOperationError('Selecione o motivo de cancelamento e informe uma justificativa.')
    command,created=Outbox.objects.get_or_create(external_order=x,target=target,defaults={'from_status':order.status,'actor':actor,'payload':payload})
    if not created:
        if command.state not in ('failed',):raise OrderOperationError('Comando já registrado; aguarde a conciliação.')
        command.state='pending';command.error='';command.payload=payload;command.from_status=order.status;command.save(update_fields=['state','error','payload','from_status'])
    event=OrderStatusEvent.objects.create(order=order,tenant=tenant,from_status=order.status,to_status=order.status,actor=actor,source='panel',note='Solicitado '+target+' à plataforma.',metadata={'channel_command':command.pk,'send_notification':False,'cancellation_code':payload.get('cancellationCode'),'justification':payload.get('reason')})
    from apps.orders.realtime import publish_order_event
    transaction.on_commit(lambda:publish_order_event(order.pk,tenant.pk))
    return order,event

def process_event(event_id):
    # Claim only the inbox row, commit, then perform slow HTTP outside order locks.
    # This keeps signed webhook persistence independent from a slow details API.
    with transaction.atomic():
        e=Inbox.objects.select_for_update(of=('self',)).select_related('connection').get(pk=event_id)
        if e.state in ('processed','ignored','blocked','processing'):return
        e.state='processing';e.next_attempt=timezone.now()+timedelta(minutes=3)
        e.save(update_fields=['state','next_attempt'])
    try:
        normalized=raw=None
        if e.code in STATES and not ExternalOrder.objects.filter(connection=e.connection,external_id=e.order_id).exists():
            api=connector(e.connection)
            raw=api.detail(e.order_id);normalized=api.normalize(raw)
        apply_event(event_id,normalized=normalized,raw=raw)
    except (ProviderError,ValueError) as exc:
        with transaction.atomic():
            Connection.objects.select_for_update().get(pk=e.connection_id)
            e=Inbox.objects.select_for_update().get(pk=event_id)
            if e.state in ('processed','ignored'):return
            e.attempts+=1
            exhausted=e.attempts>=10 or (getattr(exc,'status_code',None)==404 and timezone.now()-e.received_at>=timedelta(minutes=10))
            e.state='blocked' if exhausted else 'error'
            e.error=str(exc)[:240] if isinstance(exc,ProviderError) else 'Não foi possível interpretar o pedido externo.'
            e.next_attempt=timezone.now()+timedelta(seconds=min(3600,30*2**min(e.attempts,7)));e.save()
            Connection.objects.filter(pk=e.connection_id).update(status='error',last_error=e.error)


def process_command(command_id):
    # Commit claim BEFORE HTTP. Crash after send leaves an uncertain command,
    # never an automatic blind repeat of a non-idempotent external write.
    with transaction.atomic():
        initial=Outbox.objects.select_related('external_order').get(pk=command_id)
        Connection.objects.select_for_update().get(pk=initial.external_order.connection_id)
        ExternalOrder.objects.select_for_update().get(pk=initial.external_order_id)
        Order.objects.select_for_update().get(pk=initial.external_order.order_id)
        cmd=Outbox.objects.select_for_update(of=('self',)).select_related('external_order__connection','external_order__order').get(pk=command_id)
        if cmd.state!='pending':return
        x=cmd.external_order
        if not x.connection.enabled or x.order.status!=cmd.from_status:
            cmd.state='superseded';cmd.save(update_fields=['state']);return
        if cmd.target not in permitted(x.order,ignore_pending=True):
            cmd.state='failed';cmd.error='Transição não permitida para este pedido.';cmd.save(update_fields=['state','error']);return
        if x.connection.mode=='simulation':
            if not settings.CHANNELS_SIMULATOR_ENABLED:
                cmd.state='failed';cmd.error='Simulador desativado.';cmd.save(update_fields=['state','error']);return
            target='ready' if cmd.target=='ready_for_pickup' else cmd.target
            code=next(k for k,v in STATES.items() if v==target)
            e=receive(x.connection,{'id':f'sim-command-{cmd.pk}','orderId':x.external_id,'merchantId':x.connection.merchant_id,'code':code,'createdAt':timezone.now().isoformat()})
            apply_event(e.pk);return
        cmd.state='sending';cmd.attempts+=1;cmd.sent_at=timezone.now();cmd.save(update_fields=['state','attempts','sent_at'])
    try:
        connector(x.connection).command(x,cmd.target,cmd.payload)
        state,error='awaiting',''
    except ProviderError as exc:
        state='uncertain' if exc.uncertain else 'pending' if exc.retryable else 'failed'
        error=str(exc)
    # An event may arrive before this HTTP request completes; don't overwrite it.
    Outbox.objects.filter(pk=cmd.pk,state='sending').update(state=state,error=error,next_attempt=timezone.now()+timedelta(seconds=min(3600,30*2**min(cmd.attempts,7))))
    from apps.orders.realtime import publish_order_event
    publish_order_event(x.order_id,x.connection.tenant_id)
