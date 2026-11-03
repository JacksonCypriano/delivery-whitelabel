"""Pacote 15: no external transaction/outbox for local 99Food simulation."""
from unittest.mock import patch
from types import SimpleNamespace
from django.test import SimpleTestCase
from apps.channels.services import queue_transition


class Food99SimulationRoutingTests(SimpleTestCase):
    @patch('apps.channels.food99_simulated_operation.transition_simulated')
    @patch('apps.channels.services._queue_external_transition')
    @patch('apps.channels.services.ExternalOrder.objects')
    def test_simulation_bypasses_external_locks_and_outbox(self, objects, external, simulate):
        tenant = SimpleNamespace(pk=23)
        objects.filter.return_value.values_list.return_value.first.return_value = ('99food', 'simulation')
        expected = (SimpleNamespace(pk=42), object())
        simulate.return_value = expected
        actual = queue_transition(order_id=42, tenant=tenant, target='confirmed', actor=None)
        self.assertIs(actual, expected)
        external.assert_not_called()
        simulate.assert_called_once_with(order_id=42, tenant=tenant, target='confirmed', actor=None)

    @patch('apps.channels.food99_simulated_operation.transition_simulated')
    @patch('apps.channels.services._queue_external_transition')
    @patch('apps.channels.services.ExternalOrder.objects')
    def test_real_provider_keeps_original_queue(self, objects, external, simulate):
        tenant = SimpleNamespace(pk=23)
        objects.filter.return_value.values_list.return_value.first.return_value = ('ifood', 'test')
        expected = (SimpleNamespace(pk=42), object())
        external.return_value = expected
        actual = queue_transition(order_id=42, tenant=tenant, target='confirmed', actor=None, payload={})
        self.assertIs(actual, expected)
        simulate.assert_not_called()
        external.assert_called_once_with(42, tenant, 'confirmed', None, {})
