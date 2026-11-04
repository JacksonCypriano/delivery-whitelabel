"""Opt-in single-shop 99Food sandbox pilot tests (no external requests)."""
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.channels.connectors import ProviderError
from apps.channels.food99_auto_pilot import auto_pilot_order_new
from apps.channels.food99_staging import stage_order
from apps.channels.models import Connection, Inbox
from apps.tenants.models import Tenant

FLAGS = dict(SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
    CHANNELS_LIVE_ENABLED=False, CHANNELS_NETWORK_ENABLED=False,
    FOOD99_AUTO_PILOT_ENABLED=True, FOOD99_PILOT_BRL_CONFIRMED=True,
    FOOD99_SANDBOX_IMPORT_TO_ORDERS=True, FOOD99_REMOTE_CONFIRM_ENABLED=True,
    FOOD99_WEBHOOK_ACK_ENABLED=True, FOOD99_WEBHOOK_CAPTURE_ENABLED=True,
    FOOD99_ASYNC_RECONCILE_ENABLED=True, FOOD99_PILOT_TENANT_SLUG='pilot-test')

@override_settings(**FLAGS)
class Food99AutoPilotTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug='pilot-test', name='Pilot Test',
                                            whatsapp_number='5511999998888')
        self.conn = Connection.objects.create(tenant=self.tenant, provider='99food',
                                               mode='test', merchant_id='555', enabled=False)
        sha = 'b' * 64
        self.event = Inbox.objects.create(connection=self.conn, order_id='123456',
            code='orderNew', external_id='99food-' + sha, state='blocked',
            occurred_at=timezone.now(), payload={'food99_quarantined': True,
                'operational_enabled': False, 'app_shop_id': 'vdd-pilot-test',
                'raw_sha256': sha})

    @patch('apps.channels.food99_auto_pilot.get_order_detail')
    def test_missing_staging_does_not_access_network(self, fetch):
        with self.assertRaises(ProviderError):
            auto_pilot_order_new(self.event.pk, staged_id=98765)
        fetch.assert_not_called()

    @patch('apps.channels.food99_auto_pilot.get_order_detail')
    @override_settings(FOOD99_AUTO_PILOT_ENABLED=False)
    def test_disabled_pilot_is_inert(self, fetch):
        with self.assertRaises(ProviderError):
            auto_pilot_order_new(self.event.pk, staged_id=1)
        fetch.assert_not_called()

    @patch('apps.channels.food99_auto_pilot.get_order_detail')
    @override_settings(FOOD99_PILOT_TENANT_SLUG='other')
    def test_wrong_tenant_is_rejected(self, fetch):
        with self.assertRaises(ProviderError):
            auto_pilot_order_new(self.event.pk, staged_id=1)
        fetch.assert_not_called()

    @patch('apps.channels.food99_auto_pilot.get_order_detail')
    @override_settings(CHANNELS_LIVE_ENABLED=True)
    def test_live_settings_rejected(self, fetch):
        with self.assertRaises(ProviderError):
            auto_pilot_order_new(self.event.pk, staged_id=1)
        fetch.assert_not_called()

    @patch('apps.channels.food99_auto_pilot.get_order_detail')
    @override_settings(FOOD99_PILOT_BRL_CONFIRMED=False)
    def test_without_currency_approval_is_rejected(self, fetch):
        with self.assertRaises(ProviderError):
            auto_pilot_order_new(self.event.pk, staged_id=1)
        fetch.assert_not_called()

    @patch('apps.channels.food99_auto_pilot.confirm_existing')
    @patch('apps.channels.food99_auto_pilot.promote_reviewed')
    @patch('apps.channels.food99_auto_pilot.get_order_detail')
    def test_new_order_reaches_import_and_one_shot_confirm(self, fetch, promote, confirm):
        detail = {
            'order_id': 123456, 'status': 100,
            'shop': {'shop_id': 555, 'app_shop_id': 'vdd-pilot-test'},
            'create_time': int(timezone.now().timestamp()),
            'cancel_time': 0, 'complete_time': 0, 'shop_confirm_time': 0,
            'delivery_type': 2, 'pay_type': 1,
            'price': {'order_price': 2100, 'real_pay_price': 2100,
                      'delivery_price': 100, 'items_discount': 0, 'delivery_discount': 0},
            'order_items': [{'name': 'Pizza', 'app_item_id': 'SKU',
                             'amount': 1, 'total_price': 2000, 'sub_item_list': []}],
        }
        staged, _ = stage_order(detail, tenant=self.tenant,
                                app_shop_id='vdd-pilot-test',
                                shop_id='555', order_id='123456')
        fetch.return_value = detail
        promote.return_value = {'order_id': 777, 'imported': True}
        confirm.return_value = {'result': 'AWAITING_WEBHOOK'}
        result = auto_pilot_order_new(self.event.pk, staged_id=staged.pk)
        self.assertEqual(result['result'], 'AWAITING_WEBHOOK')
        self.assertTrue(result['imported'])
        staged.refresh_from_db()
        self.assertEqual(staged.state, 'reviewed')
        promote.assert_called_once_with(staged_id=staged.pk, apply=True, confirm_brl=True)
        confirm.assert_called_once_with(order_id=777, apply=True, confirm_remote=True)

    @patch('apps.channels.food99_auto_pilot.confirm_existing')
    @patch('apps.channels.food99_auto_pilot.promote_reviewed')
    @patch('apps.channels.food99_auto_pilot.get_order_detail')
    def test_canceled_order_does_not_import_or_confirm(self, fetch, promote, confirm):
        detail = {
            'order_id': 123456, 'status': 100,
            'shop': {'shop_id': 555, 'app_shop_id': 'vdd-pilot-test'},
            'create_time': int(timezone.now().timestamp()),
            'delivery_type': 2, 'pay_type': 1,
            'price': {'order_price': 2100, 'real_pay_price': 2100,
                      'delivery_price': 100, 'items_discount': 0, 'delivery_discount': 0},
            'order_items': [{'name': 'Pizza', 'app_item_id': 'SKU',
                             'amount': 1, 'total_price': 2000, 'sub_item_list': []}],
        }
        staged, _ = stage_order(detail, tenant=self.tenant,
                                app_shop_id='vdd-pilot-test',
                                shop_id='555', order_id='123456')
        fetch.return_value = dict(detail, cancel_time=int(timezone.now().timestamp()))
        result = auto_pilot_order_new(self.event.pk, staged_id=staged.pk)
        self.assertEqual(result['result'], 'REVIEW_REQUIRED')
        staged.refresh_from_db()
        self.assertEqual(staged.state, 'review')
        promote.assert_not_called()
        confirm.assert_not_called()
