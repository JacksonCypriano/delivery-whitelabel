"""99Food Package 14: contract-safe operational simulation, never an Order.

The report is a diagnostic derived only from tenant-scoped encrypted staging.
It MUST NOT call a provider, mutate inventory, create Order/Outbox or trigger KDS.
No external numeric status is interpreted as pending/confirmed without contract.
"""
from apps.channels.food99_operational_preview import preview_staged


CONTRACT_GATES = (
    ('status_mapping', 'Mapeamento oficial de status recebido e testado'),
    ('webhook_auth', 'Assinatura e autenticidade dos webhooks comprovadas'),
    ('event_schema', 'Schema de eventos, idempotência e ordem homologados'),
    ('money', 'Moeda e composição financeira homologadas'),
    ('remote_transitions', 'Aceite, preparo, entrega e cancelamento homologados'),
    ('end_to_end', 'Fluxo completo sandbox → Order → KDS validado'),
)


def format_dry_run(projection):
    """Return an allowlisted, PII-free immutable preview and explicit blockers."""
    items = projection['items']
    total_quantity = sum(item['quantity'] for item in items)
    line_total_minor = sum(item['line_total_minor'] for item in items)
    order_total_minor = projection['total_minor']
    gates = [{'code': key, 'label': label, 'approved': False}
             for key, label in CONTRACT_GATES]
    diagnostics = []
    if not items:
        diagnostics.append({'code': 'NO_ITEMS', 'label': 'Sem itens válidos'})
    if any(item['quantity'] < 1 for item in items):
        diagnostics.append({'code': 'INVALID_QUANTITY', 'label': 'Quantidade inválida'})
    if order_total_minor < 0:
        diagnostics.append({'code': 'NEGATIVE_TOTAL', 'label': 'Total negativo'})
    if line_total_minor != order_total_minor:
        diagnostics.append({
            'code': 'TOTAL_NOT_EQUAL_LINES',
            'label': 'A soma das linhas difere do total informado; taxas e descontos ainda não homologados',
        })
    if projection['status_code'] == 922:
        diagnostics.append({'code': 'STATUS_922_UNMAPPED', 'label': 'Status 922 não homologado'})
    return {
        'provider': '99food',
        'external_id': projection['external_id'],
        'status_code': projection['status_code'],
        'staging_state': projection['state'],
        'items_count': len(items),
        'quantity_total': total_quantity,
        'line_total_minor': line_total_minor,
        'order_total_minor': order_total_minor,
        'delivery_by': projection['delivery_by'],
        'payment_method': projection['payment_method'],
        'payment_confirmed': False,
        'currency_confirmed': False,
        'status_confirmed': False,
        'schema_confirmed': False,
        'operational_enabled': False,
        'kds_visible': False,
        'orders_created': 0,
        'allowed_transitions': [],
        'contract_gates': gates,
        'diagnostics': diagnostics,
        'message': 'Simulação exclusivamente de leitura. Não importa nem altera pedidos.',
    }


def dry_run_staged(row):
    return format_dry_run(preview_staged(row))


def dry_run_summary(projections):
    """Pure aggregator for the admin preview; no customer identifiers exposed."""
    results = [format_dry_run(p) for p in projections]
    return {
        'inspected': len(results),
        'with_diagnostics': sum(bool(r['diagnostics']) for r in results),
        'operational_enabled': False,
        'orders_created': 0,
    }
