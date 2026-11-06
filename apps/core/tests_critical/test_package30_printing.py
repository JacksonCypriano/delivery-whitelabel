import uuid
from decimal import Decimal
from django.test import Client
from apps.orders.models import Order, OrderItem, PrintDevice, PrintJob
from apps.orders.printing import ticket, enqueue, plan_thermal_jobs
from .base import CriticalTestCase


class PrintingTests(CriticalTestCase):
    def setUp(self):
        self.client=Client(HTTP_HOST=self.host(self.tenant_a));self.client.force_login(self.admin_a)
        self.order=Order.objects.create(tenant=self.tenant_a,total=20,subtotal=20,source='manual',status='confirmed',customer_name='Cliente privado',payment_method='cash',payment_change_for='50')
        OrderItem.objects.create(order=self.order,name='Produto original',quantity=1,price=20,notes='Sem cebola')
        self.device=PrintDevice.objects.create(tenant=self.tenant_a,active=True)

    def test_kitchen_privacy_and_financial_truth(self):
        text=ticket(self.order,'kitchen',58)
        self.assertIn('Sem cebola',text);self.assertNotIn('Cliente privado',text);self.assertNotIn('R$',text)
        full=ticket(self.order,'full',80)
        self.assertIn('Troco: R$ 30.00',full);self.assertIn('A cobrar: R$ 20',full)
        self.assertNotIn('PAGO ·',full)
        self.assertTrue(all(len(line)<=32 for line in text.splitlines()))

    def test_auto_dedup_and_reprint_snapshot(self):
        self.device.auto_enabled=True;self.device.templates=['kitchen'];self.device.save()
        plan_thermal_jobs();plan_thermal_jobs();self.assertEqual(PrintJob.objects.count(),1)
        original=PrintJob.objects.get()
        self.order.items.update(name='Nome alterado')
        copy=enqueue(self.device,self.order,'kitchen',str(uuid.uuid4()),original)
        self.assertIn('Produto original',copy.text);self.assertNotIn('Nome alterado',copy.text)
        self.assertIn('REIMPRESSÃO',copy.text)

    def test_device_claim_ack_once_and_tenant_scope(self):
        token=self.client.post('/api/merchant/printing/',{'action':'pair'},content_type='application/json').json()['token']
        job=enqueue(self.device,self.order,'full','manual')
        url='/integracoes/print-device/'
        def post(data,host=None): return self.client.post(url,data,content_type='application/json',HTTP_AUTHORIZATION='Bearer '+token,HTTP_HOST=host or self.host(self.tenant_a))
        self.assertEqual(post({'action':'claim'},self.host(self.tenant_b)).status_code,403)
        self.assertEqual(post({'action':'claim'}).json()['job']['id'],str(job.pk))
        self.assertIsNone(post({'action':'claim'}).json()['job'])
        self.assertEqual(post({'action':'ack','job':str(job.pk),'state':'spooled'}).json()['state'],'spooled')
        self.assertEqual(post({'action':'ack','job':str(job.pk),'state':'uncertain'}).json()['state'],'spooled')
        self.client.post('/api/merchant/printing/',{'action':'revoke'},content_type='application/json')
        self.assertEqual(post({'action':'claim'}).status_code,401)

    def test_cross_tenant_and_pickup_courier_rejected(self):
        other=Order.objects.create(tenant=self.tenant_b,total=10)
        with self.assertRaises(ValueError): enqueue(self.device,other,'full','a')
        self.order.delivery_type='pickup'
        with self.assertRaises(ValueError):ticket(self.order,'courier',80)

    def test_auto_event_survives_fast_kitchen_transition(self):
        from apps.orders.models import OrderStatusEvent
        self.device.auto_enabled=True;self.device.templates=['kitchen'];self.device.save()
        self.order.status='preparing';self.order.save()
        OrderStatusEvent.objects.create(order=self.order,tenant=self.tenant_a,from_status='pending',to_status='confirmed',source='panel')
        plan_thermal_jobs();plan_thermal_jobs()
        self.assertEqual(PrintJob.objects.count(),1)
