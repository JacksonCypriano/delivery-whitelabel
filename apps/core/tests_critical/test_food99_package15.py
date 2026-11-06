"""Package 15: HML-local 99Food operational simulation safety regression."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.channels.connectors import ProviderError
from apps.channels.food99_simulated_operation import (
    import_simulated,
    require_simulation,
    simulation_enabled,
    simulation_transitions,
)


class Food99Package15SafetyTests(TestCase):
    @override_settings(FOOD99_OPERATIONAL_SIMULATION_ENABLED=True,
                       SETTINGS_MODULE='config.settings.prod', CHANNELS_LIVE_ENABLED=False)
    def test_simulation_disabled_even_if_flag_set_in_production(self):
        self.assertFalse(simulation_enabled())
        with self.assertRaises(ProviderError):
            require_simulation()

    @override_settings(FOOD99_OPERATIONAL_SIMULATION_ENABLED=False,
                       SETTINGS_MODULE='config.settings.hml', CHANNELS_LIVE_ENABLED=False)
    def test_default_deny(self):
        self.assertFalse(simulation_enabled())

    @override_settings(FOOD99_OPERATIONAL_SIMULATION_ENABLED=True,
                       SETTINGS_MODULE='config.settings.hml', CHANNELS_LIVE_ENABLED=True)
    def test_live_enabled_disables_simulation(self):
        self.assertFalse(simulation_enabled())

    @override_settings(FOOD99_OPERATIONAL_SIMULATION_ENABLED=True,
                       SETTINGS_MODULE='config.settings.hml', CHANNELS_LIVE_ENABLED=False)
    def test_simulation_allowed_only_for_hml(self):
        self.assertTrue(simulation_enabled())

    @override_settings(FOOD99_OPERATIONAL_SIMULATION_ENABLED=True,
                       SETTINGS_MODULE='config.settings.hml', CHANNELS_LIVE_ENABLED=False)
    def test_status_is_local_and_terminal_states_reject_changes(self):
        order = SimpleNamespace(status='pending', delivery_type='delivery',
                                attribution={'food99_local_simulation':True})
        self.assertEqual(simulation_transitions(order), ['confirmed','cancelled'])
        order.status = 'preparing'
        self.assertEqual(simulation_transitions(order), ['ready'])
        order.status = 'delivered'
        self.assertEqual(simulation_transitions(order), [])
        order.attribution={}
        self.assertEqual(simulation_transitions(order), [])

    @override_settings(FOOD99_OPERATIONAL_SIMULATION_ENABLED=False,
                       SETTINGS_MODULE='config.settings.prod', CHANNELS_LIVE_ENABLED=False)
    @patch('apps.channels.food99_simulated_operation.Food99StagedOrder.objects')
    def test_import_rejected_before_db_or_provider_access(self, objects):
        with self.assertRaises(ProviderError):
            import_simulated(tenant=SimpleNamespace(pk=7), staged_id=1)
        objects.select_for_update.assert_not_called()

    @override_settings(FOOD99_OPERATIONAL_SIMULATION_ENABLED=True,
                       SETTINGS_MODULE='config.settings.hml', CHANNELS_LIVE_ENABLED=False)
    @patch('apps.channels.food99_simulated_operation.preview_staged')
    @patch('apps.channels.food99_simulated_operation.Food99StagedOrder.objects')
    def test_unreviewed_staging_cannot_create_order(self, objects, project):
        objects.select_for_update.return_value.select_related.return_value.filter.return_value.first.return_value = SimpleNamespace(state='review')
        with self.assertRaises(ProviderError):
            import_simulated(tenant=SimpleNamespace(pk=7), staged_id=1)
        project.assert_not_called()
