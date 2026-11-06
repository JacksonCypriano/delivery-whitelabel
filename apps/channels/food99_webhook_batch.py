"""Bounded, manual sandbox reconciliation of signed 99Food webhook observations.

This service cannot ACK provider callbacks, write remote status, import Orders,
run stock mutations, or enable merchant connections. Its only write is to the
existing encrypted Food99StagedOrder quarantine via reconcile(..., apply=True).
"""
from django.conf import settings
from django.db.models import Q

from .connectors import ProviderError
from .food99_webhook_reconcile import reconcile, _guard
from .models import Inbox


def reconcile_batch(*, tenant_slug, limit=20, apply=False):
    _guard()
    if not isinstance(tenant_slug, str) or not tenant_slug or len(tenant_slug) > 100:
        raise ProviderError('Tenant inválido.')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ProviderError('Limite deve estar entre 1 e 100 eventos.')
    # IDs are selected before processing. New events cannot endlessly extend this run.
    identifiers = list(Inbox.objects.filter(
        state='blocked', connection__provider='99food',
        connection__mode='test', connection__enabled=False,
        connection__tenant__slug=tenant_slug,
        payload__food99_quarantined=True,
    ).order_by('received_at', 'pk').values_list('pk', flat=True)[:limit])
    outcomes = []
    for event_id in identifiers:
        try:
            result = reconcile(event_id, apply=apply)
            outcomes.append({'event_id': event_id, 'result': result['state'], 'ok': True})
        except ProviderError:
            outcomes.append({'event_id': event_id, 'result': 'REVIEW_REQUIRED', 'ok': False})
        # Do not catch programming errors silently: fail the command instead.
    return {'selected': len(identifiers), 'ok': sum(x['ok'] for x in outcomes),
            'failed': sum(not x['ok'] for x in outcomes),
            'applied': bool(apply), 'events': outcomes}
