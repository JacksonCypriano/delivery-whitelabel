"""Isolated 99Food end-to-end sandbox pilot for a single explicitly authorized shop.

NO live support, no implicit opt-in and no inferred provider status transitions.
The unverified BRL/status=100 assumptions are permitted solely for a dedicated
sandbox pilot with explicit environment approval, not production readiness.
"""
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .connectors import ProviderError
from .food99_import import preview
from .food99_orders import get_order_detail
from .food99_remote_confirm import confirm_existing
from .food99_sandbox_promotion import promote_reviewed
from .food99_semantics import semantic_fingerprint
from .food99_webhook_reconcile import _eligible, _guard
from .models import ExternalOrder, Food99StagedOrder, Inbox


def _pilot_guard(event):
    _guard()
    if not all((
        getattr(settings, 'FOOD99_AUTO_PILOT_ENABLED', False) is True,
        getattr(settings, 'FOOD99_PILOT_BRL_CONFIRMED', False) is True,
        getattr(settings, 'FOOD99_SANDBOX_IMPORT_TO_ORDERS', False) is True,
        getattr(settings, 'FOOD99_REMOTE_CONFIRM_ENABLED', False) is True,
        getattr(settings, 'FOOD99_WEBHOOK_ACK_ENABLED', False) is True,
        getattr(settings, 'FOOD99_WEBHOOK_CAPTURE_ENABLED', False) is True,
        getattr(settings, 'FOOD99_ASYNC_RECONCILE_ENABLED', False) is True,
    )):
        raise ProviderError('Piloto 99Food exige autorização explícita de todas as proteções.')
    allowed = getattr(settings, 'FOOD99_PILOT_TENANT_SLUG', '')
    if not allowed or allowed != event.connection.tenant.slug:
        raise ProviderError('Loja fora do piloto 99Food.')
    _eligible(event)
    if event.code != 'orderNew':
        raise ProviderError('Piloto automático permite somente orderNew.')
    if event.received_at < timezone.now() - timedelta(minutes=4):
        raise ProviderError('Webhook antigo: não é seguro tentar confirmação automática.')


def auto_pilot_order_new(event_id, *, staged_id):
    """Import and request one-shot confirmation for a new signed sandbox order.

    Network operations occur outside the approval transaction; every stage
    rechecks ownership/fingerprint. No automatic retry of uncertain POST.
    """
    event = (Inbox.objects.select_related('connection__tenant')
             .filter(pk=event_id).first())
    if event is None:
        raise ProviderError('Webhook do piloto inexistente.')
    _pilot_guard(event)
    staged = (Food99StagedOrder.objects.select_related('connection__tenant')
              .filter(pk=staged_id, connection=event.connection,
                      external_id=event.order_id,
                      app_shop_id=event.payload['app_shop_id']).first())
    if staged is None:
        raise ProviderError('Revisão não corresponde ao webhook assinado.')

    # A duplicate delivery must not query the provider or re-enter confirmation
    # after a command has already been reserved, regardless of its final state.
    existing = ExternalOrder.objects.filter(
        connection=event.connection, external_id=event.order_id,
        order__tenant_id=event.connection.tenant_id, order__source='99food',
    ).first()
    if existing and existing.commands.filter(target='confirmed').exists():
        return {'event_id': event_id, 'result': 'ALREADY_REQUESTED',
                'imported': False, 'order_id': existing.order_id}

    # The first read happens before any local write. Reject old/cancelled orders.
    fresh = get_order_detail(staged.app_shop_id, staged.external_id)
    data = preview(fresh, app_shop_id=staged.app_shop_id,
                   shop_id=event.connection.merchant_id, order_id=staged.external_id)
    if (data['status_code'] != 100
            or any(fresh.get(key) not in (None, 0) for key in
                   ('cancel_time', 'complete_time', 'shop_confirm_time'))
            or data['created_at'] < timezone.now() - timedelta(minutes=3)
            or data['created_at'] > timezone.now() + timedelta(seconds=30)
            or semantic_fingerprint(data) != (staged.latest_fingerprint or staged.fingerprint)):
        return {'event_id': event_id, 'result': 'REVIEW_REQUIRED', 'imported': False}

    # Approval is sandbox-local and short-lived. Competing updates are locked.
    with transaction.atomic():
        current_event = (Inbox.objects.select_for_update()
                         .select_related('connection__tenant').get(pk=event_id))
        _pilot_guard(current_event)
        current = (Food99StagedOrder.objects.select_for_update()
                   .select_related('connection__tenant').get(pk=staged_id))
        if (current.connection_id != current_event.connection_id
                or current.external_id != current_event.order_id
                or current.app_shop_id != current_event.payload['app_shop_id']
                or (current.latest_fingerprint or current.fingerprint) != semantic_fingerprint(data)
                or current.state not in ('review', 'reviewed')):
            raise ProviderError('Revisão alterada durante o piloto.')
        current.state = 'reviewed'
        current.save(update_fields=['state', 'updated_at'])

    # Promotion does its own fresh provider GET and transaction recheck.
    promotion = promote_reviewed(staged_id=staged_id, apply=True, confirm_brl=True)
    result = confirm_existing(order_id=promotion['order_id'], apply=True,
                              confirm_remote=True)
    return {'event_id': event_id, 'result': result['result'],
            'imported': promotion['imported'], 'order_id': promotion['order_id']}
