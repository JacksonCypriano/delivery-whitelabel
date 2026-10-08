import io
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from apps.orders.models import Order,Courier,DeliveryAssignment,DeliveryAudit
from .base import CriticalTestCase

class LogisticsTests(CriticalTestCase):
    def setUp(self):
        self.client=Client(HTTP_HOST=self.host(self.tenant_a));self.client.force_login(self.admin_a)
        self.order=Order.objects.create(tenant=self.tenant_a,total=20,source='manual',status='ready',delivery_type='delivery')
        self.courier=Courier.objects.create(tenant=self.tenant_a,name='Entregador A',phone='11999999999')
    def post(self,action,**kwargs):
        return self.client.post('/api/merchant/logistics/',{'action':action,'order':self.order.pk,**kwargs},content_type='application/json')
    def test_assign_dispatch_complete_and_duplicate(self):
        self.assertEqual(self.post('assign',courier=self.courier.pk).status_code,200)
        self.assertEqual(self.post('assign',courier=self.courier.pk).status_code,200)
        self.assertEqual(DeliveryAudit.objects.count(),1)
        self.assertEqual(self.post('dispatch').status_code,200)
        self.assertEqual(self.post('complete',recipient='Cliente',latitude=0,longitude=0).status_code,200)
        self.assertEqual(self.post('complete',recipient='Cliente').status_code,200)
        self.assertEqual(DeliveryAudit.objects.count(),3)
        self.order.refresh_from_db();self.assertEqual(self.order.status,'delivered')
        a=DeliveryAssignment.objects.get(order=self.order);self.assertEqual(a.latitude,0)
        self.assertEqual(self.client.get('/api/merchant/logistics/').json()['orders'],[])

    def test_cross_tenant_pickup_inactive(self):
        other=Courier.objects.create(tenant=self.tenant_b,name='Outro',phone='11988888888')
        self.assertEqual(self.post('assign',courier=other.pk).status_code,400)
        self.courier.active=False;self.courier.save()
        self.assertEqual(self.post('assign',courier=self.courier.pk).status_code,400)
        self.order.delivery_type='pickup';self.order.save()
        self.assertEqual(self.post('assign',courier=self.courier.pk).status_code,400)

    def test_invalid_proof_rolls_back_status(self):
        self.post('assign',courier=self.courier.pk);self.post('dispatch')
        self.assertEqual(self.post('complete',recipient='Pessoa',latitude=91,longitude=0).status_code,400)
        self.order.refresh_from_db();self.assertEqual(self.order.status,'out_for_delivery')
        self.assertIsNone(DeliveryAssignment.objects.get(order=self.order).completed_at)

    def test_private_photo(self):
        self.post('assign',courier=self.courier.pk);self.post('dispatch')
        out=io.BytesIO();Image.new('RGB',(8,8)).save(out,'PNG')
        photo=SimpleUploadedFile('photo.png',out.getvalue(),content_type='image/png')
        self.assertEqual(self.client.post('/api/merchant/logistics/',{'action':'complete','order':self.order.pk,'recipient':'Cliente','photo':photo}).status_code,200)
        a=DeliveryAssignment.objects.get(order=self.order)
        path=f'/api/merchant/logistics/{a.pk}/photo/'
        self.assertEqual(self.client.get(path)['Content-Type'],'image/jpeg')
        other=Client(HTTP_HOST=self.host(self.tenant_b));other.force_login(self.admin_b)
        self.assertEqual(other.get(path).status_code,404)
