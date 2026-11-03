"""PII-free comparison of encrypted 99Food order revisions."""
import json
from apps.billing.secrets import decrypt_secret
from apps.channels.food99_import import preview
from apps.channels.connectors import ProviderError


def _safe_items(data):
    """Compare by provider product code and list position (repeated codes allowed)."""
    return [
        {'code': item['code'], 'name': item['name'], 'quantity': item['quantity'],
         'line_total_minor': int(item['line_total'] * 100),
         'options': item['options']}
        for item in data['items']
    ]


def _read(revision, row):
    try:
        raw = json.loads(decrypt_secret(revision.encrypted_snapshot))
        return preview(raw, app_shop_id=row.app_shop_id,
                       shop_id=row.connection.merchant_id, order_id=row.external_id)
    except (ValueError, TypeError, KeyError, OverflowError, ProviderError):
        raise ProviderError('Não foi possível validar esta versão do pedido.') from None


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
    product_changes = []
    for index in range(max(len(left), len(right))):
        a = left[index] if index < len(left) else None
        b = right[index] if index < len(right) else None
        if a != b:
            product_changes.append({'position': index + 1, 'before': a, 'after': b})
    return {
        'from_version': previous.version, 'to_version': current.version,
        'status': {'before': old['status_code'], 'after': new['status_code']},
        'status_changed': old['status_code'] != new['status_code'],
        'money_changes': money, 'item_changes': product_changes,
        'currency_confirmed': False, 'operational_enabled': False,
    }
