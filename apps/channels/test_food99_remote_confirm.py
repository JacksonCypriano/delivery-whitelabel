"""One-shot sandbox provider confirm, without actual HTTP or broker."""
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.channels.connectors import ProviderError
from apps.channels.models import Connection, ExternalOrder, Inbox, Outbox
from apps.channels.food99_staging import stage_order
from apps.channels.food99_remote_confirm import confirm_existing
from apps.orders.models import Order
from apps.tenants.models import Tenant

FLAGS = dict(SETTINGS_MODULE='config.settings.hml', FOOD99_SANDBOX_ENABLED=True,
             CHANNELS_LIVE_ENABLED=False, CHANNELS_NETWORK_ENABLED=False,
             FOOD99_SANDBOX_IMPORT_TO_ORDERS=True,
             FOOD99_REMOTE_CONFIRM_ENABLED=True)


@override_settings(**FLAGS)
class Food99OneShotConfirmTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Confirm Sandbox', slug='confirm-sandbox',
                                            whatsapp_number='5511999992222')
        self.conn = Connection.objects.create(tenant=self.tenant, provider='99food',
                                              mode='test', enabled=False, merchant_id='123456789')
        self.external_id = '5764698533651349996'
        self.detail = {
            'order_id': int(self.external_id), 'status': 100,
            'shop': {'shop_id': 123456789, 'app_shop_id': 'vdd-confirm-sandbox'},
            'create_time': int(timezone.now().timestamp()), 'cancel_time': 0,
            'complete_time': 0, 'shop_confirm_time': 0,
            'delivery_type': 2, 'pay_type': 1,
            'price': {'order_price': 2100, 'real_pay_price': 2100,
                      'delivery_price': 100, 'items_discount': 0, 'delivery_discount': 0},
            'order_items': [{'name':'Pizza', 'app_item_id':'PIZZA', 'amount':2,
                             'total_price':2000, 'sub_item_list':[]}],
        }
        self.stage, _ = stage_order(self.detail, tenant=self.tenant,
                       app_shop_id='vdd-confirm-sandbox', shop_id=self.conn.merchant_id,
                       order_id=self.external_id)
        self.stage.state = 'reviewed'; self.stage.save(update_fields=['state'])
        sha = 'a' * 64
        Inbox.objects.create(connection=self.conn, external_id='99food-' + sha,
            order_id=self.external_id, code='orderNew', state='blocked',
            occurred_at=timezone.now(),
            payload={'food99_quarantined': True, 'operational_enabled': False,
                     'app_shop_id': 'vdd-confirm-sandbox', 'raw_sha256': sha})
        self.order = Order.objects.create(
            tenant=self.tenant, source='99food', status='pending',
            customer_name='Cliente 99Food', total='21.00', subtotal='20.00',
            delivery_fee='1.00', delivery_type='delivery', payment_flow='marketplace',
            payment_method='online')
        self.external = ExternalOrder.objects.create(
            connection=self.conn, order=self.order, external_id=self.external_id,
            encrypted_snapshot='sandbox-test')

    def test_preview_does_not_contact_provider_or_create_command(self):
        with patch('apps.channels.food99_remote_confirm.get_order_detail') as get:
            self.assertEqual(confirm_existing(order_id=self.order.pk)['result'], 'PREVIEW')
        get.assert_not_called()
        self.assertEqual(Outbox.objects.count(), 0)

    def test_confirm_requires_all_optins(self):
        with override_settings(FOOD99_REMOTE_CONFIRM_ENABLED=False):
            with self.assertRaises(ProviderError):
                confirm_existing(order_id=self.order.pk, apply=True, confirm_remote=True)
        with self.assertRaises(ProviderError):
            confirm_existing(order_id=self.order.pk, apply=True)

    def test_production_and_live_channels_are_blocked(self):
        for flags in ({'SETTINGS_MODULE': 'config.settings.prod'},
                      {'CHANNELS_LIVE_ENABLED': True},
                      {'CHANNELS_NETWORK_ENABLED': True}):
            with override_settings(**flags):
                with self.assertRaises(ProviderError):
                    confirm_existing(order_id=self.order.pk)

    @patch('apps.channels.food99_remote_confirm._remote_confirm')
    @patch('apps.channels.food99_remote_confirm.get_order_detail')
    def test_one_shot_confirm_only_once(self, detail, remote):
        detail.return_value = self.detail
        first = confirm_existing(order_id=self.order.pk, apply=True, confirm_remote=True)
        self.assertEqual(first['result'], 'AWAITING_WEBHOOK')
        self.assertEqual(Outbox.objects.get().state, 'awaiting')
        second = confirm_existing(order_id=self.order.pk, apply=True, confirm_remote=True)
        self.assertEqual(second['result'], 'ALREADY_REQUESTED')
        remote.assert_called_once()
        detail.assert_called_once()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    @patch('apps.channels.food99_remote_confirm._remote_confirm',
           side_effect=ProviderError('network uncertain', uncertain=True))
    @patch('apps.channels.food99_remote_confirm.get_order_detail')
    def test_uncertain_write_is_never_repeated(self, detail, remote):
        detail.return_value = self.detail
        self.assertEqual(confirm_existing(order_id=self.order.pk, apply=True,
                         confirm_remote=True)['result'], 'UNCERTAIN')
        self.assertEqual(Outbox.objects.get().state, 'uncertain')
        self.assertEqual(confirm_existing(order_id=self.order.pk, apply=True,
                         confirm_remote=True)['result'], 'ALREADY_REQUESTED')
        remote.assert_called_once()

    @patch('apps.channels.food99_remote_confirm._remote_confirm')
    @patch('apps.channels.food99_remote_confirm.get_order_detail')
    def test_cancellation_between_review_and_post_blocks(self, detail, remote):
        detail.return_value = {**self.detail, 'cancel_time': int(timezone.now().timestamp())}
        with self.assertRaises(ProviderError):
            confirm_existing(order_id=self.order.pk, apply=True, confirm_remote=True)
        remote.assert_not_called()
        self.assertEqual(Outbox.objects.count(), 0)

    def test_ineligible_connection_never_sends(self):
        self.conn.enabled=True; self.conn.save(update_fields=['enabled'])
        with self.assertRaises(ProviderError):
            confirm_existing(order_id=self.order.pk)

    @patch('apps.channels.food99_remote_confirm.get_shop_token', return_value='fake-token')
    @patch('apps.channels.food99_remote_confirm.requests.post')
    def test_http_confirm_uses_official_post_body(self, post, token):
        from apps.channels.food99_remote_confirm import _remote_confirm
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {'errno':0, 'data':True}
        _remote_confirm('vdd-confirm-sandbox', self.external_id)
        self.assertEqual(post.call_args.kwargs['json']['order_id'], int(self.external_id))
        self.assertEqual(post.call_args.kwargs['json']['auth_token'], 'fake-token')
        self.assertFalse(post.call_args.kwargs['allow_redirects'])

    @patch('apps.channels.food99_remote_confirm.get_shop_token', return_value='fake-token')
    @patch('apps.channels.food99_remote_confirm.requests.post')
    def test_provider_refusal_is_uncertain(self, post, token):
        from apps.channels.food99_remote_confirm import _remote_confirm
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {'errno':1, 'data':False}
        with self.assertRaises(ProviderError):
            _remote_confirm('vdd-confirm-sandbox', self.external_id)
