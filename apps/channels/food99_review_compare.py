"""Semantic, tenant-owned, PII-limited comparison of 99Food revisions.

Order changes and reordered option siblings do not manufacture diffs.
"""
import json

from apps.billing.secrets import decrypt_secret
from apps.channels.connectors import ProviderError
from apps.channels.food99_import import preview
from apps.channels.food99_semantics import canonical_items


def _read(revision, row):
    try:
        raw = json.loads(decrypt_secret(revision.encrypted_snapshot))
        return preview(raw, app_shop_id=row.app_shop_id,
                       shop_id=row.connection.merchant_id, order_id=row.external_id)
    except (ValueError, TypeError, KeyError, OverflowError, ProviderError):
        raise ProviderError('Não foi possível validar esta versão do pedido.') from None


def _safe_items(data):
    """Return stable order-insensitive product records without customer notes."""
    return [
        {'code': item['code'], 'name': item['name'],
         'quantity': item['quantity'], 'line_total_minor': item['line_total_minor'],
         'options': item['options']}
        for item in canonical_items(data['items'])
    ]


def compare_revisions(row, previous, current):
    if previous.staged_order_id != row.pk or current.staged_order_id != row.pk:
        raise ProviderError('Versões não pertencem ao pedido selecionado.')
    old = _read(previous, row)
    new = _read(current, row)
    money_fields = ('total', 'real_pay', 'delivery_fee', 'discount')
    money = [
        {'field': field, 'before_minor': int(old[field] * 100),
         'after_minor': int(new[field] * 100)}
        for field in money_fields if old[field] != new[field]
    ]
    left, right = _safe_items(old), _safe_items(new)
    # Compare notes without ever returning their contents to the browser.
    notes_changed = [item['notes'] for item in canonical_items(old['items'])] != [
        item['notes'] for item in canonical_items(new['items'])]

    product_changes = []
    for index in range(max(len(left), len(right))):
        a = left[index] if index < len(left) else None
        b = right[index] if index < len(right) else None
        if a != b:
            product_changes.append({'position': index + 1, 'before': a, 'after': b})
    status_changed = old['status_code'] != new['status_code']
    # Legacy previews and security-test fixtures may omit these optional fields.
    # Comparing missing values as None preserves a real difference when only
    # one revision supplies a field, without assuming an operational status.
    fulfillment_changed = old.get('delivery_by') != new.get('delivery_by')
    payment_changed = (
        old.get('payment_method'), old.get('paid')
    ) != (
        new.get('payment_method'), new.get('paid')
    )
    relevant = bool(status_changed or fulfillment_changed or payment_changed or money or product_changes or notes_changed)
    return {
        'from_version': previous.version, 'to_version': current.version,
        'status': {'before': old['status_code'], 'after': new['status_code']},
        'status_changed': status_changed,
        'fulfillment_changed': fulfillment_changed,
        'payment_changed': payment_changed,
        'notes_changed': notes_changed,
        'money_changes': money, 'item_changes': product_changes,
        'semantic_changes': relevant, 'ordering_only': not relevant,
        'currency_confirmed': False, 'operational_enabled': False,
    }
