from copy import deepcopy
from decimal import Decimal
from django.test import SimpleTestCase
from .connectors import ProviderError
from .food99_import import preview, minor, fingerprint_preview


class Food99ImportTests(SimpleTestCase):
    def sample(self):
        return {'order_id':123,'status':922,'shop':{'shop_id':456,'app_shop_id':'vdd-vitrine-demo'},
                'create_time':1762100000,'delivery_type':2,'pay_type':2,
                'price':{'order_price':2100,'real_pay_price':2100,'delivery_price':100,'items_discount':0,'delivery_discount':0},
                'order_items':[{'app_item_id':'SKU1','name':'Pizza','amount':2,'total_price':2000,
                   'sub_item_list':[{'name':'Queijo','amount':1,'total_price':100,'sub_item_list':[]}]}],
                'receive_address':{'name':'DADO PRIVADO','phone':'11999999999'}}

    def parse(self,p):
        return preview(p,app_shop_id='vdd-vitrine-demo',shop_id='456',order_id='123')

    def test_units_and_nested_options(self):
        p=self.parse(self.sample())
        self.assertEqual(p['total'],Decimal('21'))
        self.assertEqual(p['items'][0]['price'],Decimal('10'))
        self.assertEqual(p['items'][0]['options'][0]['price'],'1')
        self.assertEqual(p['status_code'],922)

    def test_no_private_data_in_preview(self):
        p=self.parse(self.sample())
        self.assertNotIn('11999999999',str(p))
        self.assertNotIn('DADO PRIVADO',str(p))

    def test_wrong_merchant_rejected(self):
        x=self.sample();x['shop']['shop_id']=999
        with self.assertRaises(ProviderError):self.parse(x)

    def test_fractional_or_invalid_minor_units_rejected(self):
        x=self.sample();x['price']['order_price']=21.0
        with self.assertRaises(ProviderError):self.parse(x)
        with self.assertRaises(ProviderError):minor(-1)

    def test_invalid_quantity_rejected(self):
        x=self.sample();x['order_items'][0]['amount']=0
        with self.assertRaises(ProviderError):self.parse(x)

    def test_invalid_delivery_rejected(self):
        x=self.sample();x['delivery_type']=999
        with self.assertRaises(ProviderError):self.parse(x)

    def test_no_missing_money_fields_or_floats(self):
        x=self.sample(); x['price']['real_pay_price']=None
        with self.assertRaises(ProviderError): self.parse(x)
        x=self.sample(); x['order_items'][0]['total_price']=2000.0
        with self.assertRaises(ProviderError): self.parse(x)

    def test_money_composition_below_zero_rejected(self):
        x=self.sample(); x['price']['order_price']=0; x['price']['delivery_price']=100
        with self.assertRaises(ProviderError): self.parse(x)

    def test_malformed_additional_rejected(self):
        x=self.sample(); x['order_items'][0]['sub_item_list']=[{'name':'Cheese','amount':0}]
        with self.assertRaises(ProviderError): self.parse(x)

    def test_status_is_preserved_not_guessed(self):
        x=self.sample(); x['status']=922
        result=self.parse(x)
        self.assertEqual(result['status_code'],922)
        self.assertFalse(result['currency_confirmed'])

    def test_fingerprint_is_stable_and_sensitive_to_financial_changes(self):
        sample = self.sample()
        a = fingerprint_preview(self.parse(sample))
        self.assertEqual(a, fingerprint_preview(self.parse(deepcopy(sample))))
        sample['price']['order_price'] += 1
        self.assertNotEqual(a, fingerprint_preview(self.parse(sample)))

    def test_fingerprint_excludes_customer_pii(self):
        sample = self.sample()
        a = fingerprint_preview(self.parse(sample))
        sample['receive_address']['phone'] = 'OUTRO_NUMERO'
        sample['receive_address']['name'] = 'OUTRO_NOME'
        self.assertEqual(a, fingerprint_preview(self.parse(sample)))

    def test_fingerprint_detects_modified_options(self):
        sample = self.sample()
        a = fingerprint_preview(self.parse(sample))
        sample['order_items'][0]['sub_item_list'][0]['total_price'] += 100
        self.assertNotEqual(a, fingerprint_preview(self.parse(sample)))
