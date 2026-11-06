from django.test import SimpleTestCase
from apps.channels.connectors import ProviderError
from apps.channels.food99_mapping_probe import inspect_order


class OrderMappingProbeTests(SimpleTestCase):
    def sample(self):
        return {'order_id': 123, 'status': 1, 'shop': {'shop_id': 456, 'app_shop_id': 'vdd-vitrine-demo'},
                'price': {'order_price': 1200, 'real_pay_price': 1300, 'currency': 'BRL'},
                'order_items': [{'name': 'Produto', 'amount': 1, 'total_price': 1200}],
                'delivery_type': 1, 'pay_type': 1, 'create_time': 1720000000,
                'receive_address': {'name': 'NÃO PODE SAIR NO SUMÁRIO', 'phone': '11999999999'}}

    def inspect(self, data):
        return inspect_order(data, order_id='123', app_shop_id='vdd-vitrine-demo', shop_id='456')

    def test_summary_safe(self):
        result = self.inspect(self.sample())
        self.assertTrue(result['shop_match'])
        self.assertTrue(result['price_minor_units'])
        self.assertNotIn('11999999999', str(result))
        self.assertNotIn('NÃO PODE SAIR', str(result))

    def test_wrong_shop_rejected(self):
        data = self.sample(); data['shop']['shop_id'] = 999
        with self.assertRaises(ProviderError): self.inspect(data)

    def test_wrong_order_rejected(self):
        data = self.sample(); data['order_id'] = 999
        with self.assertRaises(ProviderError): self.inspect(data)

    def test_invalid_money_rejected(self):
        data = self.sample(); data['price']['real_pay_price'] = '13.00'
        with self.assertRaises(ProviderError): self.inspect(data)

    def test_no_items_rejected(self):
        data = self.sample(); data['order_items'] = []
        with self.assertRaises(ProviderError): self.inspect(data)
