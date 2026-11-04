"""Isolated, opt-in 99Food sandbox actions. Never used for production or iFood.

Every remote write is reserved before HTTP and is executed at most once. The
local Order is only advanced by an authenticated provider event (except for
purely internal preparation/dispatch stages).
"""
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.orders.models import Order, OrderStatusEvent
from apps.orders.operations import OrderOperationError
from apps.orders.realtime import publish_order_event
from .models import Connection, ExternalOrder, Outbox

REASONS = frozenset((1010, 1020, 1030, 1040, 1050, 1060, 1070,
                     1071, 1072, 1073, 1074, 1080))
SELF_ONLY = frozenset((1060, 1071, 1072))
WAITING = frozenset(('pending', 'sending', 'awaiting', 'uncertain'))


def _enabled():
    return (getattr(settings, 'SETTINGS_MODULE', '') == 'config.settings.hml'
            and getattr(settings, 'FOOD99_SANDBOX_ENABLED', False) is True
            and getattr(settings, 'FOOD99_SANDBOX_ACTIONS_ENABLED', False) is True
            and getattr(settings, 'FOOD99_WEBHOOK_CAPTURE_ENABLED', False) is True
            and getattr(settings, 'FOOD99_WEBHOOK_ACK_ENABLED', False) is True
            and getattr(settings, 'FOOD99_ASYNC_RECONCILE_ENABLED', False) is True
            and getattr(settings, 'FOOD99_LOCAL_EVENT_SYNC_ENABLED', False) is True
            and getattr(settings, 'CHANNELS_LIVE_ENABLED', False) is False
            and getattr(settings, 'CHANNELS_NETWORK_ENABLED', False) is False)


def _owned(x):
    return (x.connection.provider == '99food' and x.connection.mode == 'test'
            and x.connection.enabled is False and x.order.source == '99food'
            and x.order.tenant_id == x.connection.tenant_id
            and x.connection.tenant.slug == getattr(settings, 'FOOD99_PILOT_TENANT_SLUG', '')
            and bool(getattr(settings, 'FOOD99_PILOT_TENANT_SLUG', '')))


def permitted_sandbox(order):
    if not _enabled():
        return []
    x = getattr(order, 'external_order', None)
    if x is None or not _owned(x) or order.status in ('delivered', 'cancelled'):
        return []
    if x.cancellation_state == 'requested' or x.commands.filter(state__in=WAITING).exists():
        return []
    if order.status == 'confirmed':
        return ['preparing', 'ready', 'cancelled']
    if order.status == 'preparing':
        return ['ready', 'cancelled']
    if order.status in ('ready', 'ready_for_pickup'):
        if order.delivery_type == 'pickup':
            return ['delivered', 'cancelled']
        if x.delivery_by == 'MERCHANT':
            return ['out_for_delivery', 'cancelled']
        return ['cancelled']
    if order.status == 'out_for_delivery' and x.delivery_by == 'MERCHANT':
        return ['delivered']
    return []


def _reason(payload, delivery_by):
    value = (payload or {}).get('cancellationCode')
    try:
        code = int(value)
    except (ValueError, TypeError):
        raise OrderOperationError('Selecione um motivo de cancelamento da 99Food.') from None
    if code not in REASONS or (code in SELF_ONLY and delivery_by != 'MERCHANT'):
        raise OrderOperationError('Motivo de cancelamento não permitido para esta entrega.')
    reason = (payload or {}).get('reason') or ''
    if not isinstance(reason, str) or len(reason.strip()) > 500:
        raise OrderOperationError('Justificativa inválida (máximo de 500 caracteres).')
    if code == 1080 and not reason.strip():
        raise OrderOperationError('Descreva o motivo do cancelamento (código 1080).')
    return {'reason_id': code, 'reason': reason.strip()}


def queue_sandbox_transition(order_id, tenant, target, actor=None, payload=None):
    if not _enabled():
        raise OrderOperationError('Operações 99Food sandbox desativadas.')
    # Lock hierarchy: Connection -> ExternalOrder -> Order, matching webhook consumers.
    with transaction.atomic():
        x0 = ExternalOrder.objects.select_related('connection').filter(
            order_id=order_id, order__tenant=tenant,
            connection__provider='99food', connection__mode='test').first()
        if x0 is None:
            raise OrderOperationError('Pedido sandbox não encontrado.')
        conn = Connection.objects.select_for_update().get(pk=x0.connection_id)
        x = (ExternalOrder.objects.select_for_update()
             .select_related('connection__tenant', 'order').get(pk=x0.pk))
        order = Order.objects.select_for_update().get(pk=x.order_id, tenant=tenant)
        if not _owned(x) or target not in permitted_sandbox(order):
            if target == order.status:
                return order, None
            raise OrderOperationError('Transição não autorizada para a 99Food.')
        if x.commands.filter(target=target).exists():
            raise OrderOperationError('A operação já foi solicitada; não reenviar automaticamente.')
        reason = _reason(payload, x.delivery_by) if target == 'cancelled' else {}
        # Internal stages have no documented remote endpoint.
        if target in ('preparing', 'out_for_delivery'):
            before = order.status
            order.status, order.status_updated_at = target, timezone.now()
            order.save(update_fields=['status', 'status_updated_at'])
            event = OrderStatusEvent.objects.create(
                order=order, tenant=tenant, from_status=before, to_status=target,
                actor=actor if getattr(actor, 'is_authenticated', False) else None,
                source='panel', note='Etapa interna do pedido 99Food (sandbox).',
                metadata={'send_notification': False, 'food99_local_only': True})
            transaction.on_commit(lambda: publish_order_event(order.pk, tenant.pk))
            return order, event
        # External actions only via explicit one-shot Outbox reservation.
        if target == 'ready':
            action = 'ready'
        elif target == 'delivered' and order.delivery_type == 'pickup':
            action = 'finish'
        elif target == 'delivered' and x.delivery_by == 'MERCHANT':
            action = 'delivered'
        elif target == 'cancelled':
            action = 'cancel'
        else:
            raise OrderOperationError('Operação não disponível para este tipo de entrega.')
        cmd = Outbox.objects.create(
            external_order=x, target=target, from_status=order.status,
            actor=actor if getattr(actor, 'is_authenticated', False) else None,
            payload={'food99_sandbox_action': action, **reason}, state='pending')
        event = OrderStatusEvent.objects.create(
            order=order, tenant=tenant, from_status=order.status,
            to_status=order.status,
            actor=actor if getattr(actor, 'is_authenticated', False) else None,
            source='panel', note='Solicitado à 99Food (sandbox): ' + action,
            metadata={'channel_command': cmd.pk, 'send_notification': False})
        if target == 'cancelled':
            x.cancellation_state = 'requested'
            x.cancellation_requested_at = timezone.now()
            x.save(update_fields=['cancellation_state', 'cancellation_requested_at'])
        def enqueue():
            from .tasks import send_99food_sandbox_action
            try:
                send_99food_sandbox_action.delay(cmd.pk)
            except Exception:
                # Durable pending Outbox remains available for explicit recovery.
                pass
            publish_order_event(order.pk, tenant.pk)
        transaction.on_commit(enqueue)
        return order, event


def send_reserved_action(command_id):
    """Explicit one-shot worker. Never retry a POST with uncertain outcome."""
    import requests
    from .food99_auth import BASE_URL, get_shop_token
    from .food99_orders import get_order_detail

    if not _enabled():
        return {'result': 'DISABLED', 'sent': False}
    cmd = (Outbox.objects.select_related('external_order__connection__tenant',
                                        'external_order__order')
           .filter(pk=command_id).first())
    if not cmd or cmd.state != 'pending' or not _owned(cmd.external_order):
        return {'result': 'NOT_ELIGIBLE', 'sent': False}
    x = cmd.external_order
    action = cmd.payload.get('food99_sandbox_action')
    if action not in ('ready', 'delivered', 'finish', 'cancel'):
        return {'result': 'INVALID_ACTION', 'sent': False}
    # Only a read is performed before reserving the irreversible command.
    try:
        detail = get_order_detail('vdd-' + x.connection.tenant.slug, x.external_id)
        status = detail.get('status')
        valid = status == 200 if action in ('ready', 'finish', 'cancel') else status in (200, 400, 500)
        if (not valid or detail.get('cancel_time') not in (None, 0)
                or detail.get('complete_time') not in (None, 0)):
            raise ValueError('Pedido externo mudou de estado.')
    except Exception:
        Outbox.objects.filter(pk=cmd.pk, state='pending').update(
            state='failed', error='Pré-validação remota indisponível; revise o pedido.')
        if action == 'cancel':
            ExternalOrder.objects.filter(pk=x.pk, cancellation_state='requested').update(
                cancellation_state='rejected',
                cancellation_error='Não foi possível validar o cancelamento junto à 99Food.')
        return {'result': 'PREFLIGHT_FAILED', 'sent': False}
    with transaction.atomic():
        conn = Connection.objects.select_for_update().get(pk=x.connection_id)
        locked = (ExternalOrder.objects.select_for_update()
                  .select_related('connection__tenant', 'order').get(pk=x.pk))
        order = Order.objects.select_for_update().get(pk=locked.order_id)
        cmd = Outbox.objects.select_for_update().get(pk=cmd.pk)
        # The queued command itself makes permitted_sandbox() return [];
        # validate its reserved transition directly under the same locks.
        allowed = (
            (action == 'ready' and cmd.target == 'ready' and
             order.status in ('confirmed', 'preparing')) or
            (action == 'delivered' and cmd.target == 'delivered' and
             locked.delivery_by == 'MERCHANT' and order.status == 'out_for_delivery') or
            (action == 'finish' and cmd.target == 'delivered' and
             order.delivery_type == 'pickup' and order.status in ('ready', 'ready_for_pickup')) or
            (action == 'cancel' and cmd.target == 'cancelled' and
             order.status in ('confirmed', 'preparing', 'ready', 'ready_for_pickup') and
             locked.cancellation_state == 'requested')
        )
        if (not _enabled() or not _owned(locked) or cmd.state != 'pending'
                or cmd.from_status != order.status
                or cmd.payload.get('food99_sandbox_action') != action
                or not allowed
                or locked.commands.filter(state__in=WAITING).exclude(pk=cmd.pk).exists()):
            return {'result': 'NOT_ELIGIBLE', 'sent': False}
        cmd.state = 'sending'
        cmd.attempts = 1
        cmd.sent_at = timezone.now()
        cmd.save(update_fields=['state', 'attempts', 'sent_at'])
    payload = {'order_id': int(x.external_id)}
    if action == 'cancel':
        payload.update(reason_id=cmd.payload['reason_id'], reason=cmd.payload['reason'])
    # Network happens AFTER the transaction commits its one-shot reservation.
    try:
        payload['auth_token'] = get_shop_token('vdd-' + x.connection.tenant.slug)
        response = requests.post(
            BASE_URL + '/v1/order/order/' + action,
            json=payload, timeout=(3, 7), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError('HTTP unsuccessful')
        data = response.json()
        if not isinstance(data, dict) or data.get('errno') != 0:
            raise ValueError('Provider rejected operation')
        if action == 'cancel' and data.get('data') is not True:
            raise ValueError('Cancellation unconfirmed')
        if action != 'cancel' and not isinstance(data.get('data'), dict):
            raise ValueError('Unexpected response schema')
        result = 'AWAITING_WEBHOOK'
        state = 'awaiting'
        error = ''
    except Exception:
        # A failure AFTER reservation is always uncertain, including token errors.
        # Never retry automatically or expose provider response/customer details.
        result = 'UNCERTAIN'
        state = 'uncertain'
        error = 'Resultado remoto incerto: consultar a 99Food; nunca reenviar automaticamente.'
    Outbox.objects.filter(pk=cmd.pk, state='sending').update(state=state, error=error)
    return {'result': result, 'sent': True}
