"""Bounded, cursor-based 99Food sandbox Inbox replay for *already imported* Orders.

Never calls 99Food, imports Orders, retries a remote POST, or enables live mode.
The existing row-locked sync_existing() owns all state transitions and idempotency.
Only explicitly invoked by an operator; not a periodic Celery task.
"""
from django.db.models import Exists, OuterRef

from .connectors import ProviderError
from .food99_local_sync import EVENT_TO_STATUS, _sync_guard, sync_existing
from .food99_webhook_reconcile import _eligible
from .models import ExternalOrder, Inbox


def _check_args(tenant_slug, limit, cursor):
    _sync_guard()
    if not isinstance(tenant_slug, str) or not tenant_slug or len(tenant_slug) > 100:
        raise ProviderError('Tenant inválido.')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ProviderError('Limite deve estar entre 1 e 100.')
    if type(cursor) is not int or cursor < 0:
        raise ProviderError('Cursor inválido.')


def _candidate_query(tenant_slug, cursor):
    linked = ExternalOrder.objects.filter(
        connection_id=OuterRef('connection_id'), external_id=OuterRef('order_id'),
        order__tenant_id=OuterRef('connection__tenant_id'), order__source='99food',
    )
    return (Inbox.objects.select_related('connection__tenant').filter(
        pk__gt=cursor, state='blocked', connection__provider='99food',
        connection__mode='test', connection__enabled=False,
        connection__tenant__slug=tenant_slug,
        payload__food99_quarantined=True,
        code__in=tuple(EVENT_TO_STATUS),
    ).annotate(_has_imported_order=Exists(linked)).filter(
        _has_imported_order=True,
    ).order_by('pk'))


def plan_backlog(*, tenant_slug, limit=50, cursor=0):
    """Read-only page of candidates with proof of signed quarantine envelope.

    Scans up to ``limit`` imported, supported events; an invalid envelope is
    reported and skipped at apply-time, rather than blocking future pages.
    Cursor advances even if no event is eligible for application.
    """
    _check_args(tenant_slug, limit, cursor)
    records = list(_candidate_query(tenant_slug, cursor)[:limit + 1])
    more = len(records) > limit
    page = records[:limit]
    results = []
    for event in page:
        try:
            _eligible(event)
            result = 'READY'
        except ProviderError:
            result = 'INVALID_ENVELOPE'
        results.append({'event_id': event.pk, 'code': event.code,
                        'order_id': event.order_id, 'result': result})
    return {
        'tenant': tenant_slug, 'sandbox_only': True, 'read_only': True,
        'cursor': cursor, 'next_cursor': page[-1].pk if more and page else None,
        'last_scanned_id': page[-1].pk if page else cursor,
        'has_more': more, 'selected': len(page),
        'ready': sum(x['result'] == 'READY' for x in results),
        'invalid': sum(x['result'] == 'INVALID_ENVELOPE' for x in results),
        'events': results, 'provider_writes': 0,
    }


def run_backlog(*, tenant_slug, limit=50, cursor=0, apply=False):
    """Preview by default. Apply each eligible event via the row-locked consumer.

    A concurrent worker can process the same event first; sync_existing handles
    that through ALREADY_HANDLED. Invalid envelopes remain quarantined.
    """
    page = plan_backlog(tenant_slug=tenant_slug, limit=limit, cursor=cursor)
    results = []
    for event in page['events']:
        if event['result'] != 'READY':
            results.append({'event_id': event['event_id'], 'result': 'INVALID_ENVELOPE',
                            'applied': False})
            continue
        try:
            result = sync_existing(event['event_id'], apply=apply)
        except ProviderError:
            result = {'event_id': event['event_id'], 'result': 'REVIEW_REQUIRED',
                      'applied': False}
        results.append(result)
    return {**page, 'read_only': not apply, 'applied': bool(apply),
            'updated': sum(bool(r.get('applied')) for r in results),
            'results': results}
