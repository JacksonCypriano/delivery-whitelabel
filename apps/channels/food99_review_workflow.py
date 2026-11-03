"""Local review workflow for 99Food test orders; never promotes to Orders/KDS.

The state 'reviewed' acknowledges that a human saw a specific latest fingerprint,
NOT that the external status, currency, payment or callback contract is approved.
"""
from django.db import transaction
from django.utils import timezone
from apps.channels.connectors import ProviderError
from apps.channels.models import Food99StagedOrder
from apps.channels.food99_orders import get_order_detail
from apps.channels.food99_staging import stage_order


@transaction.atomic
def acknowledge_review(*, tenant, pk, fingerprint):
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise ProviderError('Versão informada inválida.')
    row = (Food99StagedOrder.objects.select_for_update()
           .select_related('connection').filter(
               pk=pk, connection__tenant=tenant,
               connection__provider='99food', connection__mode='test').first())
    if row is None:
        raise ProviderError('Pedido não encontrado para esta loja.')
    if row.connection.enabled:
        raise ProviderError('Revisão bloqueada: conexão operacional habilitada.')
    current = row.latest_fingerprint or row.fingerprint
    if fingerprint != current:
        raise ProviderError('Pedido atualizado desde a abertura da revisão; recarregue a página.')
    if row.state != 'reviewed':
        row.state = 'reviewed'
        row.save(update_fields=['state', 'updated_at'])
        return row, 'REVIEWED'
    return row, 'ALREADY_REVIEWED'


def refresh_staged_order(*, tenant, pk):
    """Fetch one previously registered sandbox order and update quarantine only.

    No transaction is held across network I/O; stage_order rechecks tenant and
    enabled state with row locks after the response arrives.
    """
    row = (Food99StagedOrder.objects.select_related('connection')
           .filter(pk=pk, connection__tenant=tenant,
                   connection__provider='99food', connection__mode='test').first())
    if row is None:
        raise ProviderError('Pedido não encontrado para esta loja.')
    if row.connection.enabled:
        raise ProviderError('Atualização bloqueada: conexão operacional habilitada.')
    detail = get_order_detail(row.app_shop_id, row.external_id)
    refreshed, result = stage_order(
        detail, tenant=tenant, app_shop_id=row.app_shop_id,
        shop_id=row.connection.merchant_id, order_id=row.external_id)
    return refreshed, result


def status_policy(code):
    """Unconfirmed external status must never be treated as an active order."""
    return {'code': code, 'mapped': False, 'operational_status': None,
            'reason': 'Contrato de estados da 99Food ainda não homologado.'}
