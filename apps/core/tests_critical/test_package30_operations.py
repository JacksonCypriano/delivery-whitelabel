from datetime import timedelta
from unittest.mock import patch
from django.test import Client
from django.utils import timezone
from apps.orders.models import Order
from .base import CriticalTestCase


class BoardEvolutionTests(CriticalTestCase):
    def setUp(self):
        self.client=Client(HTTP_HOST=self.host(self.tenant_a));self.client.force_login(self.admin_a)

    def test_completed_today_includes_old_order_not_previous_completion(self):
        old=Order.objects.create(tenant=self.tenant_a,total=10,source='manual',status='delivered')
        previous=Order.objects.create(tenant=self.tenant_a,total=10,source='manual',status='delivered')
        Order.objects.filter(pk=old.pk).update(created_at=timezone.now()-timedelta(days=3))
        Order.objects.filter(pk=previous.pk).update(status_updated_at=timezone.now()-timedelta(days=3))
        Order.objects.create(tenant=self.tenant_b,total=10,source='manual',status='delivered')
        d=self.client.get('/api/merchant/orders/').json()
        self.assertEqual([o['id'] for o in d['delivered']],[old.pk])
        self.assertNotIn(old.pk,[o['id'] for o in d['all_orders']])

    def test_all_history_cancelled_filters_and_validation(self):
        a=Order.objects.create(tenant=self.tenant_a,total=10,source='manual',status='cancelled',customer_name='Ana')
        Order.objects.create(tenant=self.tenant_a,total=10,source='manual',customer_name='Bia')
        d=self.client.get('/api/merchant/orders/',{'q':'Ana','history_status':'cancelled'}).json()
        self.assertEqual([o['id'] for o in d['all_orders']],[a.pk])
        self.assertEqual(self.client.get('/api/merchant/orders/',{'period':'custom','start':'bad','end':'bad'}).status_code,400)

    def test_stale_transition_never_calls_existing_service(self):
        order=Order.objects.create(tenant=self.tenant_a,total=10,source='manual',status='confirmed')
        with patch('apps.merchant.orders.transition_order') as service:
            response=self.client.post(f'/api/merchant/orders/{order.pk}/transition/',{'status':'preparing','expected_status_updated_at':(timezone.now()-timedelta(hours=1)).isoformat()},content_type='application/json')
        self.assertEqual(response.status_code,409);service.assert_not_called()
        order.refresh_from_db();self.assertEqual(order.status,'confirmed')
