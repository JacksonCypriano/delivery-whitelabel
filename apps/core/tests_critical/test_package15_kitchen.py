from decimal import Decimal
from django.test import Client
from apps.orders.models import Order
from .base import CriticalTestCase

class KitchenTests(CriticalTestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=self.host(self.tenant_a))
        self.client.force_login(self.admin_a)
        self.order = Order.objects.create(tenant=self.tenant_a, source='manual', status='confirmed', delivery_type='pickup', total=Decimal('20'))

    def post(self, body, pk=None):
        return self.client.post(f'/api/merchant/kitchen/{pk or self.order.pk}/', body, content_type='application/json')

    def test_only_kitchen_orders_are_listed(self):
        Order.objects.create(tenant=self.tenant_a, source='manual', status='delivered', total=20)
        Order.objects.create(tenant=self.tenant_b, source='manual', status='confirmed', total=20)
        data = self.client.get('/api/merchant/kitchen/').json()
        self.assertEqual([o['id'] for o in data['orders']], [self.order.pk])
        self.assertEqual([a['value'] for a in data['orders'][0]['allowed_transitions']], ['preparing', 'ready_for_pickup'])

    def test_pickup_flow_and_shared_audit(self):
        self.assertEqual(self.post({'status':'preparing'}).status_code, 200)
        self.assertEqual(self.post({'status':'ready_for_pickup'}).status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'ready_for_pickup')
        self.assertEqual(self.order.status_events.first().metadata['origin'], 'kds')
        self.assertEqual(self.post({'status':'out_for_delivery'}).status_code, 400)

    def test_priority_idempotent_without_status_notification(self):
        self.assertEqual(self.post({'priority': True}).status_code, 200)
        self.assertEqual(self.post({'priority': True}).status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.kitchen_priority)
        self.assertEqual(self.order.status_events.count(), 1)
        self.assertFalse(hasattr(self.order.status_events.first(), 'notification'))

    def test_priority_boolean_and_cross_tenant(self):
        self.assertEqual(self.post({'priority':'yes'}).status_code, 400)
        other = Order.objects.create(tenant=self.tenant_b, source='manual', status='confirmed', total=20)
        self.assertEqual(self.post({'priority':True},other.pk).status_code, 404)

    def test_finished_order_cannot_reenter_kitchen(self):
        self.order.status='delivered';self.order.save(update_fields=['status'])
        self.assertEqual(self.post({'status':'preparing'}).status_code,400)
