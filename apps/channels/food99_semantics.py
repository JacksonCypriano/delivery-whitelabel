"""Canonical, PII-free (after hashing) 99Food order comparison.

The order of products and option siblings is not commercially meaningful here.
The canonical form preserves duplicate entries (multiset), product codes,
quantities, names, notes, option quantities and prices. The provider's options
were already flattened by preview(); this module does not invent hierarchy.
"""
import hashlib
import json


def canonical_options(options):
    """A stable multiset. Never deduplicate options of the same name."""
    values = [
        {'option_name': str(option['option_name']), 'price': str(option['price'])}
        for option in options
    ]
    return sorted(values, key=lambda v: (v['option_name'], v['price']))


def canonical_items(items):
    result = []
    for item in items:
        result.append({
            'code': str(item['code']),
            'name': str(item['name']),
            'quantity': int(item['quantity']),
            'line_total_minor': int(item['line_total'] * 100),
            'notes': str(item.get('notes') or ''),
            'options': canonical_options(item['options']),
        })
    # Use a JSON serialization of the complete item as a deterministic sort key.
    return sorted(result, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))


def canonical_order(data):
    return {
        'shop_id': str(data['shop_id']),
        'order_id': str(data['order_id']),
        'status_code': data['status_code'],
        'delivery_by': data['delivery_by'],
        'payment_method': data['payment_method'],
        'paid': data['paid'],
        'total_minor': int(data['total'] * 100),
        'real_pay_minor': int(data['real_pay'] * 100),
        'delivery_fee_minor': int(data['delivery_fee'] * 100),
        'discount_minor': int(data['discount'] * 100),
        'items': canonical_items(data['items']),
    }


def semantic_fingerprint(data):
    canonical = canonical_order(data)
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def semantic_changes(before, after):
    """Return only PII-safe fields; item lists can contain merchant notes."""
    previous, current = canonical_order(before), canonical_order(after)
    changes = {}
    for field in ('status_code', 'delivery_by', 'payment_method', 'paid',
                  'total_minor', 'real_pay_minor', 'delivery_fee_minor', 'discount_minor'):
        if previous[field] != current[field]:
            changes[field] = {'before': previous[field], 'after': current[field]}
    return changes
