"""Opt-in sandbox projection of signed 99Food events onto already imported Orders.

Never imports a new order, consumes stock, changes payment, ACKs a callback or
writes to 99Food. Events are durable in Inbox and deduplicated transactionally.
Unknown event types/codes stay quarantined for an operator to inspect.
"""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order, OrderStatusEvent
from apps.orders.realtime import publish_order_event
from .connectors import ProviderError
from .food99_webhook_reconcile import _eligible, _guard
from .models import Connection, ExternalOrder, Inbox

# These are *named* events from the documented webhook contract, not guessed
# numeric status codes. Keep terminal events terminal and reject regressions.
EVENT_TO_STATUS = {
    'orderConfirm': 'confirmed',
    'orderReady': 'ready',
    'orderFinish': 'delivered',
    'orderCancel': 'cancelled',
}
RANK = {'pending': 0, 'confirmed': 1, 'preparing': 2,
        'ready': 3, 'ready_for_pickup': 3, 'out_for_delivery': 4,
        'delivered': 5, 'cancelled': 6}
TERMINAL = frozenset({'cancelled', 'delivered'})


def _sync_guard():
    _guard()
    if getattr(settings, 'FOOD99_LOCAL_EVENT_SYNC_ENABLED', False) is not True:
        raise ProviderError('Sincronização local 99Food desativada.')
    if getattr(settings, 'FOOD99_SANDBOX_IMPORT_TO_ORDERS', False) is not True:
        raise ProviderError('Importação sandbox desativada: sincronização indisponível.')


def sync_existing(event_id, *, apply=False):
    """Read-only by default. When enabled, updates existing sandbox Orders only.

    Lock ordering matches channel services: Connection -> ExternalOrder -> Order
    -> Inbox. No external network calls or external commands are performed.
    """
    _sync_guard()
    if type(event_id) is not int or event_id <= 0:
        raise ProviderError('ID do evento inválido.')
    original = Inbox.objects.select_related('connection__tenant').filter(pk=event_id).first()
    if original is None:
        raise ProviderError('Evento não encontrado.')
    if original.state in ('processed', 'ignored'):
        return {'event_id': event_id, 'result': 'ALREADY_HANDLED', 'applied': False}
    _eligible(original)
    target = EVENT_TO_STATUS.get(original.code)
    if not target:
        return {'event_id': event_id, 'result': 'REVIEW_REQUIRED', 'applied': False}
    linked = ExternalOrder.objects.select_related('order').filter(
        connection_id=original.connection_id, external_id=original.order_id,
        order__source='99food', order__tenant_id=original.connection.tenant_id,
    ).first()
    if linked is None:
        return {'event_id': event_id, 'result': 'NOT_IMPORTED', 'applied': False}
    if not apply:
        return {'event_id': event_id, 'result': 'PREVIEW', 'target': target,
                'order_id': linked.order_id, 'applied': False}

    with transaction.atomic():
        conn = Connection.objects.select_for_update().get(pk=original.connection_id)
        if conn.enabled or conn.provider != '99food' or conn.mode != 'test':
            raise ProviderError('Conexão 99Food não elegível.')
        x = ExternalOrder.objects.select_for_update().filter(
            connection=conn, external_id=original.order_id,
            order__tenant_id=conn.tenant_id, order__source='99food',
        ).first()
        if x is None:
            raise ProviderError('Pedido 99Food não encontrado para esta loja.')
        order = Order.objects.select_for_update().get(pk=x.order_id)
        event = Inbox.objects.select_for_update().select_related('connection__tenant').get(pk=event_id)
        if event.state in ('processed', 'ignored'):
            return {'event_id': event_id, 'result': 'ALREADY_HANDLED', 'applied': False}
        _eligible(event)
        if (event.connection_id != original.connection_id
                or event.external_id != original.external_id
                or event.order_id != original.order_id or event.code != original.code):
            raise ProviderError('Evento alterado durante a operação.')

        # Compare provider event time, not arrival time. Never roll backwards
        # nor re-open terminal Orders based on delayed webhook observations.
        if (x.last_event_at and event.occurred_at < x.last_event_at):
            reason = 'STALE'
        elif order.status in TERMINAL and order.status != target:
            reason = 'TERMINAL_CONFLICT'
        elif target != 'cancelled' and RANK.get(order.status, 99) > RANK[target]:
            reason = 'REGRESSION'
        elif order.status == target:
            reason = 'NO_CHANGE'
        else:
            reason = None
        if reason:
            # Terminal conflict remains blocked: human review is necessary.
            if reason == 'TERMINAL_CONFLICT':
                return {'event_id': event_id, 'result': reason, 'applied': False}
            if reason == 'NO_CHANGE':
                x.commands.filter(target=target, state__in=['sending', 'awaiting', 'uncertain']).update(
                    state='confirmed', error='')
                x.last_event_at = event.occurred_at
                x.save(update_fields=['last_event_at'])
                event.state = 'processed'
                event.error = ''
                event.save(update_fields=['state', 'error'])
                return {'event_id': event_id, 'result': reason, 'applied': False}
            event.state = 'ignored'
            event.error = reason
            event.save(update_fields=['state', 'error'])
            return {'event_id': event_id, 'result': reason, 'applied': False}

        before = order.status
        order.status = target
        order.status_updated_at = event.occurred_at
        order.save(update_fields=['status', 'status_updated_at'])
        x.last_event_at = event.occurred_at
        x.save(update_fields=['last_event_at'])
        x.commands.filter(target=target, state__in=['sending', 'awaiting', 'uncertain']).update(
            state='confirmed', error='')
        if target in TERMINAL:
            x.commands.filter(state__in=['sending', 'awaiting', 'uncertain', 'pending']).exclude(
                target=target).update(state='superseded', error='Estado terminal recebido da 99Food.')
        event.state = 'processed'
        event.error = ''
        event.save(update_fields=['state', 'error'])
        OrderStatusEvent.objects.create(
            order=order, tenant=conn.tenant, from_status=before, to_status=target,
            source='system', note='Webhook assinado 99Food (sandbox)',
            metadata={'external_event': event.external_id, 'send_notification': False},
        )
        transaction.on_commit(lambda: publish_order_event(order.pk, conn.tenant_id))
        return {'event_id': event_id, 'result': 'UPDATED', 'order_id': order.pk,
                'target': target, 'applied': True}


def sync_batch(*, tenant_slug, limit=50, apply=False):
    _sync_guard()
    if not isinstance(tenant_slug, str) or not tenant_slug or len(tenant_slug) > 100:
        raise ProviderError('Tenant inválido.')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ProviderError('Limite deve estar entre 1 e 100.')
    ids = list(Inbox.objects.filter(
        state='blocked', connection__provider='99food', connection__mode='test',
        connection__enabled=False, connection__tenant__slug=tenant_slug,
        payload__food99_quarantined=True,
    ).order_by('occurred_at', 'pk').values_list('pk', flat=True)[:limit])
    results = []
    for event_id in ids:
        try:
            results.append(sync_existing(event_id, apply=apply))
        except ProviderError:
            results.append({'event_id': event_id, 'result': 'REVIEW_REQUIRED', 'applied': False})
    return {'selected': len(ids), 'updated': sum(r['applied'] for r in results),
            'events': results, 'applied': bool(apply)}
