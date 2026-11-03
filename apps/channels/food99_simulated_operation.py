"""HML-only 99Food simulation isolated from provider network, payments, inventory and notices.

No official numeric status is interpreted. This is an operational exercise, not
an acknowledgment or webhook from 99Food.
"""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.channels.connectors import ProviderError
from apps.channels.models import Connection, ExternalOrder, Food99StagedOrder, Inbox
from apps.channels.food99_operational_preview import preview_staged
from apps.orders.choices import Status
from apps.orders.models import Order, OrderItem, OrderStatusEvent
from apps.orders.operations import OrderOperationError, BASE_TRANSITIONS, record_initial_event


def simulation_enabled():
    module = getattr(settings, 'SETTINGS_MODULE', '')
    return bool(getattr(settings, 'FOOD99_OPERATIONAL_SIMULATION_ENABLED', False)
                and module in ('config.settings.hml', 'config.settings.dev', 'config.settings.test')
                and not getattr(settings, 'CHANNELS_LIVE_ENABLED', False))


def require_simulation():
    if not simulation_enabled():
        raise ProviderError('Simulação operacional indisponível neste ambiente.')


@transaction.atomic
def import_simulated(*, tenant, staged_id, actor=None):
    require_simulation()
    row = (Food99StagedOrder.objects.select_for_update().select_related('connection')
           .filter(pk=staged_id, connection__tenant=tenant,
                   connection__provider='99food', connection__mode='test',
                   connection__enabled=False).first())
    if not row:
        raise ProviderError('Revisão sandbox não encontrada para esta loja.')
    if row.state != "reviewed":
        raise ProviderError("Conclua a revisão antes de criar uma simulação.")
    # Validated allowlist: no customer PII, no provider webhook/status contract.
    projection = preview_staged(row)
    if not projection['items']:
        raise ProviderError('Pedido sem produtos válidos.')
    # One simulation connection per tenant. The test connection remains disabled.
    merchant_id = f'vdd-local-simulation-{tenant.pk}'
    conn, _ = Connection.objects.select_for_update().get_or_create(
        provider='99food', mode='simulation', merchant_id=merchant_id,
        defaults={'tenant':tenant, 'merchant_name':'99Food · Simulação local',
                  'enabled':True, 'status':'simulation'})
    if conn.tenant_id != tenant.pk:
        raise ProviderError('Conexão de simulação pertence a outra loja.')
    if not conn.enabled:
        conn.enabled = True
        conn.save(update_fields=['enabled'])
    existing = ExternalOrder.objects.select_related('order').filter(
        connection=conn, external_id=row.external_id).first()
    if existing:
        if existing.order.tenant_id != tenant.pk:
            raise ProviderError('Pedido simulado associado a outra loja.')
        return existing.order, False
    # The financial values are only displayed for the operational exercise.
    # They must never be treated as verified provider settlement.
    from decimal import Decimal
    total = Decimal(projection['total_minor']) / 100
    order = Order.objects.create(
        tenant=tenant, source='99food', status=Status.PENDING,
        customer_name='Cliente 99Food (SIMULAÇÃO)', customer_phone='',
        subtotal=total, total=total, delivery_fee=0, discount_amount=0,
        delivery_type='pickup' if projection['delivery_by']=='PICKUP' else 'delivery',
        payment_flow='marketplace_due', payment_method='simulation',
        attribution={'food99_local_simulation': True, 'staged_review_id': row.pk},
    )
    for item in projection['items']:
        qty = item['quantity']
        line_price = Decimal(item['line_total_minor']) / 100 / qty
        OrderItem.objects.create(
            order=order, name=item['name'][:255], quantity=qty,
            price=line_price.quantize(Decimal('0.01')),
            product_key='', notes='', combination_details={
                'external_line_total': str(Decimal(item['line_total_minor']) / 100),
                'customizations': [{'option_name':o['name'], 'price':o['price']}
                                   for o in item['options']],
            })
    ExternalOrder.objects.create(
        connection=conn, order=order, external_id=row.external_id,
        delivery_by=projection['delivery_by'], paid=False,
        payment_summary='SIMULAÇÃO — pagamento não confirmado',
        encrypted_snapshot='', financials={
            'sandbox_simulated':True, 'staged_review_id':row.pk,
            'provider_status_unmapped':projection['status_code'],
            'currency_confirmed':False, 'payment_confirmed':False},
        warning='SIMULAÇÃO HML: sem envio à 99Food, sem estoque, pagamento ou WhatsApp.',
    )
    record_initial_event(order, actor=actor, note='Pedido 99Food simulado em homologação.')
    return order, True


def simulation_transitions(order):
    """Local exercise transitions, never provider transitions."""
    if not simulation_enabled() or not order.attribution.get('food99_local_simulation'):
        return []
    allowed = list(BASE_TRANSITIONS.get(order.status, ()))
    if order.delivery_type == 'pickup':
        allowed = [Status.READY_FOR_PICKUP if t == Status.READ else t for t in allowed]
    return allowed


@transaction.atomic
def transition_simulated(*, order_id, tenant, target, actor=None, source="panel"):
    require_simulation()
    order = (Order.objects.select_for_update(of=('self',)).select_related('external_order__connection')
             .filter(pk=order_id, tenant=tenant, source='99food').first())
    if not order:
        raise OrderOperationError('Pedido simulado não encontrado.')
    ext = getattr(order, 'external_order', None)
    if (not ext or ext.connection.mode != 'simulation'
            or not order.attribution.get('food99_local_simulation')):
        raise OrderOperationError('Pedido externo não é simulação local.')
    if target == order.status:
        return order, None
    if target not in simulation_transitions(order):
        raise OrderOperationError('Transição não permitida na simulação.')
    previous = order.status
    order.status = target
    order.status_updated_at = timezone.now()
    order.save(update_fields=['status','status_updated_at'])
    event = OrderStatusEvent.objects.create(
        order=order, tenant=tenant, from_status=previous, to_status=target,
        actor=actor if getattr(actor,'is_authenticated',False) else None,
        source=source, note='SIMULAÇÃO 99Food: alteração somente local.',
        metadata={'food99_local_simulation':True,'send_notification':False,
                  'provider_command_created':False},
    )
    return order, event


@transaction.atomic
def advance_simulated_event(*, tenant, order_id):
    """Replay one deterministic synthetic event into the local state machine.

    It is NOT an external webhook: no HTTP provider ingress and no real event
    signature interpretation. Event keys remain unique across repeated clicks.
    """
    require_simulation()
    order = (Order.objects.select_for_update(of=('self',)).select_related('external_order__connection')
             .filter(pk=order_id, tenant=tenant, source='99food').first())
    if order is None or not order.attribution.get('food99_local_simulation'):
        raise ProviderError('Pedido de simulação não encontrado.')
    ext = getattr(order, 'external_order', None)
    if ext is None or ext.connection.mode != 'simulation':
        raise ProviderError('Pedido não pertence ao simulador.')
    path = ([Status.PENDING, Status.CONFIRMED, Status.PREPARING,
             Status.READY_FOR_PICKUP, Status.DELIVERED] if order.delivery_type == 'pickup' else
            [Status.PENDING, Status.CONFIRMED, Status.PREPARING,
             Status.READY, Status.OUT_FOR_DELIVERY, Status.DELIVERED])
    if order.status not in path or order.status == path[-1]:
        return order, False
    target = path[path.index(order.status) + 1]
    if target not in simulation_transitions(order):
        raise ProviderError('Próxima transição automática não permitida.')
    event_key = f'sim-{order.pk}-{target}'
    inbox, created = Inbox.objects.get_or_create(
        connection=ext.connection, external_id=event_key,
        defaults={'order_id':ext.external_id, 'code':f'SIM_{target.upper()}',
                  'occurred_at':timezone.now(), 'payload':{
                      'simulated':True, 'target':target, 'order_pk':order.pk,
                  }, 'state':'processed'})
    if not created:
        if inbox.order_id != ext.external_id or inbox.code != f'SIM_{target.upper()}':
            raise ProviderError('Identificador de evento sintético reutilizado.')
        # Existing event and a pending order indicate corruption; never advance.
        raise ProviderError('Evento simulado repetido ou estado inconsistente.')
    result, event = transition_simulated(order_id=order.pk, tenant=tenant,
                                          target=target, source='system')
    return result, bool(event)
