"""Regression tests for comparing older 99Food preview formats."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from apps.channels.food99_review_compare import compare_revisions


class Food99ComparisonCompatibilityTests(SimpleTestCase):
    def setUp(self):
        self.row = SimpleNamespace(pk=3)
        self.old_revision = SimpleNamespace(version=1, staged_order_id=3)
        self.new_revision = SimpleNamespace(version=2, staged_order_id=3)
        self.base = {
            'status_code': 922,
            'total': Decimal('10.00'),
            'real_pay': Decimal('10.00'),
            'delivery_fee': Decimal('0'),
            'discount': Decimal('0'),
            'items': [{
                'code': 'pizza', 'name': 'Pizza', 'quantity': 1,
                'line_total': Decimal('10.00'), 'options': [], 'notes': ''
            }],
        }

    @patch('apps.channels.food99_review_compare._read')
    def test_missing_optional_fields_do_not_raise(self, read):
        read.side_effect = [self.base, {**self.base, 'total': Decimal('12.00')}]
        result = compare_revisions(self.row, self.old_revision, self.new_revision)
        self.assertEqual(result['money_changes'][0]['after_minor'], 1200)
        self.assertFalse(result['fulfillment_changed'])
        self.assertFalse(result['payment_changed'])
        self.assertFalse(result['operational_enabled'])

    @patch('apps.channels.food99_review_compare._read')
    def test_newly_present_optional_field_counts_as_change(self, read):
        read.side_effect = [
            self.base,
            {**self.base, 'delivery_by': 'MERCHANT', 'payment_method': 'cash', 'paid': False},
        ]
        result = compare_revisions(self.row, self.old_revision, self.new_revision)
        self.assertTrue(result['fulfillment_changed'])
        self.assertTrue(result['payment_changed'])
        self.assertTrue(result['semantic_changes'])
        self.assertFalse(result['operational_enabled'])
