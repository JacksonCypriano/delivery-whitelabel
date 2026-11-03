"""Fail-closed, PII-limited 99Food operational preflight.

These previews are not Order objects. No provider transition, webhook processing,
stock mutation, customer notification or KDS publication is performed here.
"""
import json

from apps.billing.secrets import decrypt_secret
from apps.channels.connectors import ProviderError
from apps.channels.food99_import import preview
from apps.channels.food99_review_workflow import status_policy


BLOCKERS = (
    ('status_contract', 'Estados externos ainda não homologados'),
    ('callback_auth', 'Assinatura e esquema dos webhooks ainda não homologados'),
    ('financial_contract', 'Moeda, pagamentos e composição financeira não homologados'),
    ('remote_transitions', 'Transições remotas sem contrato operacional homologado'),
)


def readiness(*, sandbox_enabled, connection, staged_count, reviewed_count, statuses):
    """Present actual readiness rather than implying an unverified live integration."""
    blockers = [{'code': key, 'detail': label} for key, label in BLOCKERS]
    if not sandbox_enabled:
        blockers.insert(0, {'code': 'sandbox_disabled', 'detail': 'Sandbox de testes desabilitado'})
    if connection is None:
        blockers.insert(0, {'code': 'connection_missing', 'detail': 'Nenhuma loja sandbox vinculada'})
    elif connection.enabled:
        blockers.insert(0, {'code': 'unsafe_connection', 'detail': 'Conexão de teste habilitada para operações; revisar configuração'})
    for code in sorted(set(statuses)):
        if not status_policy(code)['mapped']:
            blockers.append({'code': 'unmapped_status', 'status': code,
                             'detail': f'Status externo {code} não homologado'})
    return {
        'provider': '99food', 'mode': 'test',
        'sandbox_linked': connection is not None,
        'staged_count': staged_count,
        'reviewed_count': reviewed_count,
        'operational_enabled': False, 'can_promote_orders': False,
        'can_receive_webhooks': False, 'can_send_transitions': False,
        'blockers': blockers,
    }


def _safe_order(data, *, state, external_id):
    """Read-only presentation shaped for later Orders/KDS integration.

    The object deliberately excludes customer PII and is always non-operational.
    """
    items = []
    for item in data['items']:
        items.append({
            'name': item['name'], 'quantity': item['quantity'],
            'line_total_minor': int(item['line_total'] * 100),
            'option_count': len(item['options']),
            'options': [
                {'name': option['option_name'], 'price': option['price']}
                for option in item['options']
            ],
            # Never expose a provider-supplied customer instruction in this
            # operational preflight: free text can contain personal information.
        })
    return {
        'channel': '99food', 'channel_label': '99Food',
        'external_id': external_id, 'status_code': data['status_code'],
        'status_policy': status_policy(data['status_code']),
        'state': state, 'items': items,
        'item_count': sum(item['quantity'] for item in data['items']),
        'total_minor': int(data['total'] * 100),
        'payment_method': data['payment_method'],
        'paid_unverified': data['paid'],
        'delivery_by': data['delivery_by'],
        'preview_only': True, 'operational_enabled': False,
        'allowed_transitions': [], 'kds_visible': False,
        'payment_confirmed': False, 'currency_confirmed': False,
        'message': 'Prévia do sandbox: não é um pedido ativo e não aparece no KDS.',
    }


def preview_staged(row):
    """Validate encrypted snapshot against the fixed owner of a staged order."""
    if row.connection.provider != '99food' or row.connection.mode != 'test':
        raise ProviderError('Apenas pedidos sandbox 99Food podem ser visualizados.')
    if row.connection.enabled:
        raise ProviderError('Conexão de teste habilitada indevidamente.')
    try:
        raw = json.loads(decrypt_secret(
            row.latest_encrypted_snapshot or row.encrypted_snapshot
        ))
        data = preview(raw, app_shop_id=row.app_shop_id,
                       shop_id=row.connection.merchant_id, order_id=row.external_id)
    except (ValueError, KeyError, TypeError, OverflowError, ProviderError):
        raise ProviderError('Prévia operacional indisponível para este pedido.') from None
    return _safe_order(data, state=row.state, external_id=row.external_id)
