"""Isolated 99Food sandbox event consumer; no automatic remote writes.

The webhook ACK is for durable receipt only, never proof of operational
acceptance. Reconciliation snapshots are encrypted. Existing KDS orders are
projected only behind a separate explicit gate; absent orders stay quarantined
for review until provider status and financial mappings are certified.
"""
from django.conf import settings

from .connectors import ProviderError
from .food99_async_reconcile import _async_guard
from .food99_webhook_reconcile import reconcile
from .food99_local_sync import sync_existing
from .models import Inbox


def consume_event(event_id):
    _async_guard()
    if type(event_id) is not int or event_id <= 0:
        raise ProviderError('Evento 99Food inválido.')
    row = Inbox.objects.select_related('connection__tenant').filter(pk=event_id).first()
    if row is None:
        raise ProviderError('Evento 99Food inexistente.')
    if row.connection.provider != '99food' or row.connection.mode != 'test':
        raise ProviderError('Origem de evento 99Food inválida.')
    if row.state in ('processed', 'ignored'):
        return {'event_id': event_id, 'result': 'ALREADY_HANDLED'}
    # Always read the provider's current details, not the possibly stale body.
    result = reconcile(event_id, apply=True)
    if (row.code == 'orderNew' and
            getattr(settings, 'FOOD99_AUTO_PILOT_ENABLED', False) is True):
        from .food99_auto_pilot import auto_pilot_order_new
        return auto_pilot_order_new(event_id, staged_id=result['staged_id'])
    if (getattr(settings, 'FOOD99_LOCAL_EVENT_SYNC_ENABLED', False) is True
            and getattr(settings, 'FOOD99_SANDBOX_IMPORT_TO_ORDERS', False) is True):
        projection = sync_existing(event_id, apply=True)
        return {'event_id': event_id, 'result': projection['result'],
                'staged': result['staged']}
    return {'event_id': event_id, 'result': 'STAGED_REVIEW_REQUIRED',
            'staged': result['staged']}
