"""Regression for reorder-safe 99Food staging and visual comparisons."""
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.channels.food99_semantics import (
    canonical_items, semantic_fingerprint,
)
from apps.channels.food99_review_compare import compare_revisions


def sample():
    return {
        'shop_id': 'shop', 'order_id': 'order', 'status_code': 922,
        'delivery_by': 'MERCHANT', 'payment_method': 'cash', 'paid': False,
        'total': Decimal('185'), 'real_pay': Decimal('183.99'),
        'delivery_fee': Decimal('1'), 'discount': Decimal('9'),
        'items': [
            {'code': 'A', 'name': 'Pizza Atum', 'notes': '', 'quantity': 1,
             'line_total': Decimal('59'), 'options': [
                 {'option_name': '1× Bacon Crocante', 'price': '5'},
                 {'option_name': '1× Borda Recheada', 'price': '12'},
             ]},
            {'code': 'B', 'name': 'Pizza Calabresa', 'notes': '', 'quantity': 1,
             'line_total': Decimal('64'), 'options': []},
        ],
    }


class Food99SemanticTests(SimpleTestCase):
    def test_reordered_options_and_items_do_not_change_fingerprint(self):
        old = sample()
        changed_order = deepcopy(old)
        changed_order['items'].reverse()
        changed_order['items'][-1]['options'].reverse()
        self.assertEqual(semantic_fingerprint(old), semantic_fingerprint(changed_order))

    def test_repeated_options_are_not_deduplicated(self):
        original = sample()
        duplicate = deepcopy(original)
        duplicate['items'][0]['options'].append(deepcopy(duplicate['items'][0]['options'][0]))
        self.assertNotEqual(semantic_fingerprint(original), semantic_fingerprint(duplicate))

    def test_real_changes_change_fingerprint(self):
        for update in ('quantity', 'price', 'status', 'notes', 'name', 'payment'):
            altered = deepcopy(sample())
            if update == 'quantity': altered['items'][0]['quantity'] = 2
            if update == 'price': altered['items'][0]['options'][0]['price'] = '6'
            if update == 'status': altered['status_code'] = 923
            if update == 'notes': altered['items'][0]['notes'] = 'sem cebola'
            if update == 'name': altered['items'][0]['name'] = 'Pizza Atum Especial'
            if update == 'payment': altered['payment_method'] = 'online'
            with self.subTest(update=update):
                self.assertNotEqual(semantic_fingerprint(sample()), semantic_fingerprint(altered))

    @patch('apps.channels.food99_review_compare._read')
    def test_comparison_ignores_order_only_changes(self, read):
        before = sample()
        after = deepcopy(before)
        after['items'].reverse()
        after['items'][-1]['options'].reverse()
        read.side_effect = [before, after]
        row = SimpleNamespace(pk=10)
        earlier = SimpleNamespace(version=1, staged_order_id=10)
        later = SimpleNamespace(version=2, staged_order_id=10)
        delta = compare_revisions(row, earlier, later)
        self.assertEqual(delta['item_changes'], [])
        self.assertFalse(delta['semantic_changes'])
        self.assertTrue(delta['ordering_only'])
        self.assertFalse(delta['operational_enabled'])

    @patch('apps.channels.food99_review_compare._read')
    def test_comparison_detects_real_product_change(self, read):
        old = sample()
        new = deepcopy(old)
        new['items'][0]['options'][0]['price'] = '7'
        read.side_effect = [old, new]
        result = compare_revisions(SimpleNamespace(pk=11),
            SimpleNamespace(version=1, staged_order_id=11),
            SimpleNamespace(version=2, staged_order_id=11))
        self.assertTrue(result['semantic_changes'])
        self.assertEqual(len(result['item_changes']), 1)

    def test_canonicalization_keeps_duplicates(self):
        data = sample()['items']
        self.assertEqual(len(canonical_items(data)), 2)
