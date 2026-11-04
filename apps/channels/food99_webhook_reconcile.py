"""Manual, read-only reconciliation of signed 99Food webhook observations.

This is NOT the operational event worker: it never ACKs provider webhooks,
imports Orders, publishes KDS events, changes payments/stock, or sends writes.
"""
import re

from django.conf import settings
from django.db import transaction

from .connectors import ProviderError
from .food99_orders import get_order_detail
from .food99_staging import stage_order
from .models import Inbox, Connection
from .webhook_99food import ORDER_EVENTS

_HASH_KEY = re.compile(r"^99food-[0-9a-f]{64}$")
_ORDER_ID = re.compile(r"^[0-9]{1,30}$")


def _guard():
    if (getattr(settings, 'SETTINGS_MODULE', '') != 'config.settings.hml'
            or not getattr(settings, 'FOOD99_SANDBOX_ENABLED', False)
            or getattr(settings, 'CHANNELS_LIVE_ENABLED', False)
            or getattr(settings, 'CHANNELS_NETWORK_ENABLED', False)):
        raise ProviderError('Reconciliação manual disponível somente no sandbox isolado de HML.')


def _eligible(event):
    """Recheck the ownership and all persisted envelope identifiers."""
    p = event.payload
    c = event.connection
    if (event.state != 'blocked' or c.provider != '99food'
            or c.mode != 'test' or c.enabled
            or not isinstance(p, dict) or p.get('food99_quarantined') is not True
            or p.get('operational_enabled') is not False
            or not isinstance(event.external_id, str)
            or not _HASH_KEY.fullmatch(event.external_id)
            or p.get('raw_sha256') != event.external_id.removeprefix('99food-')
            or event.code not in ORDER_EVENTS
            or not isinstance(event.order_id, str)
            or not _ORDER_ID.fullmatch(event.order_id)
            or p.get('app_shop_id') != 'vdd-' + c.tenant.slug
            or Connection.objects.filter(
                provider='99food', mode='test', tenant=c.tenant,
                enabled=False, merchant_id=c.merchant_id
            ).count() != 1):
        raise ProviderError('Evento 99Food não elegível para reconciliação manual.')


def reconcile(event_id, *, apply=False):
    """Preview by default; --apply reads provider details and stages encrypted snapshot.

    Never updates Inbox.state to processed: the real consumer is not ready.
    Avoids transaction locks during external HTTP. stage_order revalidates
    connection ownership under row locks and deduplicates revisions.
    """
    _guard()
    try:
        event_id = int(event_id)
    except (TypeError, ValueError, OverflowError):
        raise ProviderError('ID interno do evento inválido.') from None
    if event_id <= 0:
        raise ProviderError('ID interno do evento inválido.')
    event = Inbox.objects.select_related('connection__tenant').filter(pk=event_id).first()
    if event is None:
        raise ProviderError('Evento 99Food não encontrado.')
    _eligible(event)
    result = {'event_id': event.pk, 'event_type': event.code,
              'order_id': event.order_id, 'app_shop_id': event.payload['app_shop_id'],
              'state': 'QUARANTINED', 'acknowledged': False,
              'operational': False, 'staged': False}
    if not apply:
        return result
    # No transaction held while waiting for the 99Food API.
    detail = get_order_detail(result['app_shop_id'], result['order_id'])
    # The official order detail must be validated against this connection by
    # stage_order/preview. Re-read the event before committing a staging change.
    with transaction.atomic():
        locked = Inbox.objects.select_for_update().select_related(
            'connection__tenant'
        ).get(pk=event_id)
        _eligible(locked)
        if (locked.connection_id != event.connection_id
                or locked.external_id != event.external_id
                or locked.order_id != event.order_id
                or locked.code != event.code):
            raise ProviderError('Evento alterado durante a reconciliação.')
        row, outcome = stage_order(
            detail, tenant=locked.connection.tenant,
            app_shop_id=result['app_shop_id'],
            shop_id=locked.connection.merchant_id,
            order_id=locked.order_id,
        )
    result.update(state=outcome, staged=True, staged_id=row.pk)
    return result
