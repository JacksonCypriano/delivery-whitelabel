"""Scoped, bounded read-only sandbox ingestion and refresh.

Never allows a merchant to choose an arbitrary provider shop ID; the linked
connection and app_shop_id are determined solely from the authenticated tenant.
"""
import re

from django.conf import settings
from django.core.cache import cache
from apps.channels.connectors import ProviderError
from apps.channels.models import Connection, Food99StagedOrder
from apps.channels.food99_orders import get_order_detail
from apps.channels.food99_staging import stage_order
from apps.channels.food99_review_workflow import refresh_staged_order

ORDER_ID = re.compile(r'^[0-9]{1,30}$')
MAX_BATCH = 5


def _sandbox_connection(tenant):
    if not getattr(settings, 'FOOD99_SANDBOX_ENABLED', False):
        raise ProviderError('Sandbox 99Food indisponível.')
    matches = list(Connection.objects.filter(
        tenant=tenant, provider='99food', mode='test',
        enabled=False,
    ).exclude(merchant_id__startswith='request-').order_by('pk')[:2])
    if len(matches) != 1:
        raise ProviderError('É necessário exatamente um estabelecimento sandbox vinculado.')
    return matches[0]


def stage_by_id(*, tenant, order_id):
    """GET of a single 99Food order followed by tenant-locked quarantine only."""
    if not isinstance(order_id, str) or not ORDER_ID.fullmatch(order_id):
        raise ProviderError('Identificador de pedido inválido.')
    conn = _sandbox_connection(tenant)
    cache_key = f'food99-stage-id:{conn.pk}:{order_id}'
    if not cache.add(cache_key, 'busy', 30):
        raise ProviderError('Consulta já solicitada recentemente.')
    try:
        app_shop_id = 'vdd-' + tenant.slug
        detail = get_order_detail(app_shop_id, order_id)
        staged, result = stage_order(detail, tenant=tenant,
            app_shop_id=app_shop_id, shop_id=conn.merchant_id, order_id=order_id)
        return staged, result
    except Exception:
        cache.delete(cache_key)
        raise


def refresh_batch(*, tenant, ids):
    """Update up to five *existing* sandbox rows; never process other tenants."""
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_BATCH:
        raise ProviderError('Selecione de 1 a 5 pedidos para atualizar.')
    if any(type(pk) is not int or pk < 1 for pk in ids) or len(set(ids)) != len(ids):
        raise ProviderError('Identificadores de revisão inválidos ou repetidos.')
    found = {row.pk for row in Food99StagedOrder.objects.filter(
        pk__in=ids, connection__tenant=tenant,
        connection__provider='99food', connection__mode='test',
        connection__enabled=False,
    )}
    if found != set(ids):
        raise ProviderError('Um ou mais pedidos não pertencem à loja.')
    results = []
    for pk in ids:
        throttle = f'food99-batch-refresh:{tenant.pk}:{pk}'
        if not cache.add(throttle, 'busy', 40):
            results.append({'id': pk, 'result': 'RATE_LIMITED'})
            continue
        try:
            refreshed, outcome = refresh_staged_order(tenant=tenant, pk=pk)
            results.append({'id': pk, 'result': outcome,
                            'status_code': refreshed.last_seen_status})
        except ProviderError:
            cache.delete(throttle)
            results.append({'id': pk, 'result': 'REFRESH_FAILED'})
    return results
