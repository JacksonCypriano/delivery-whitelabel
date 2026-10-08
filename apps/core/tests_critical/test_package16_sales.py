from datetime import datetime, time, timedelta
from unittest.mock import patch
from django.test import Client, override_settings
from django.utils import timezone
from apps.customers.models import Customer
from apps.tenants.models import BusinessHour
from apps.orders.models import Order, Cart, CartItem, SalesSettings, SalesMessage, MarketingConsent, OrderFeedback
from apps.orders.scheduling import validate_schedule
from apps.orders.cart_service import CartError
from apps.orders.sales import plan_sales_messages, deliver_sales_message
from apps.integrations.models import TenantWhatsAppAgent
from .base import CriticalTestCase

class SalesTests(CriticalTestCase):
    def setUp(self):
        self.client=Client(HTTP_HOST=self.host(self.tenant_a));self.client.force_login(self.admin_a)
        self.customer=Customer.objects.create(user=self.admin_a,phone='11987654321',phone_verified=True)
        self.cfg=SalesSettings.objects.create(tenant=self.tenant_a,scheduling_enabled=True,recovery_enabled=True,feedback_enabled=True,reactivation_enabled=True)
        self.now=timezone.make_aware(datetime(2026,10,8,12,0))
        self.consent=MarketingConsent.objects.create(tenant=self.tenant_a,customer=self.customer,allowed=True)
        self.cart=Cart.objects.create(tenant=self.tenant_a,user=self.admin_a)
        CartItem.objects.create(cart=self.cart,product=self.product_a,name='Produto',price=20,quantity=1)
        Cart.objects.filter(pk=self.cart.pk).update(updated_at=self.now-timedelta(hours=2));self.cart.refresh_from_db()

    def test_schedule_disabled_invalid_and_hours(self):
        target=self.now+timedelta(hours=2)
        with patch('apps.orders.scheduling.timezone.now',return_value=self.now):
            for tenant,value in [(self.tenant_b,target),(self.tenant_a,'garbage'),(self.tenant_a,target)]:
                with self.assertRaises(CartError): validate_schedule(tenant,value,'pickup')
            BusinessHour.objects.create(tenant=self.tenant_a,weekday=target.weekday(),is_closed=False,opening_time=time(10),closing_time=time(23))
            self.assertEqual(validate_schedule(self.tenant_a,target,'pickup'),target)
            for value in [self.now+timedelta(minutes=5),self.now+timedelta(days=8)]:
                with self.assertRaises(CartError): validate_schedule(self.tenant_a,value,'pickup')

    def test_schedule_crosses_midnight(self):
        target=timezone.make_aware(datetime(2026,10,9,1,0))
        BusinessHour.objects.create(tenant=self.tenant_a,weekday=3,is_closed=False,opening_time=time(18),closing_time=time(2))
        with patch('apps.orders.scheduling.timezone.now',return_value=self.now):
            self.assertEqual(validate_schedule(self.tenant_a,target,'delivery'),target)

    def test_planning_idempotent_and_opt_in(self):
        with patch('apps.orders.sales.timezone.now',return_value=self.now),patch('apps.orders.sales.deliver_sales_message'):
            plan_sales_messages();plan_sales_messages()
        self.assertEqual(SalesMessage.objects.count(),1)
        self.consent.allowed=False;self.consent.save();SalesMessage.objects.all().delete()
        with patch('apps.orders.sales.timezone.now',return_value=self.now): plan_sales_messages()
        self.assertEqual(SalesMessage.objects.count(),0)

    def notice(self,kind='recovery',order=None):
        return SalesMessage.objects.create(tenant=self.tenant_a,customer=self.customer,kind=kind,key=f'cart:{self.cart.pk}:{self.cart.checkout_token}',cart=self.cart,order=order)

    @override_settings(WHATSAPP_AGENT_ENABLED=True)
    def test_completed_purchase_suppresses_recovery(self):
        notice=self.notice()
        Order.objects.create(tenant=self.tenant_a,customer=self.customer,source='manual',source_cart_id=self.cart.pk,total=20)
        Order.objects.filter(source_cart_id=self.cart.pk).update(created_at=self.now)
        with patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text') as send:
            self.assertEqual(deliver_sales_message(notice.pk),'skipped');send.assert_not_called()

    @override_settings(WHATSAPP_AGENT_ENABLED=True)
    def test_revoked_consent_suppresses_pending_message(self):
        notice=self.notice();self.consent.allowed=False;self.consent.save()
        self.assertEqual(deliver_sales_message(notice.pk),'skipped')

    @override_settings(WHATSAPP_AGENT_ENABLED=True)
    def test_sent_once_and_cooldown(self):
        TenantWhatsAppAgent.objects.create(tenant=self.tenant_a,instance_name='test-sales',instance_created=True,status='open')
        notice=self.notice()
        with patch('apps.orders.sales.timezone.now',return_value=self.now),patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text',return_value='ok') as send:
            self.assertEqual(deliver_sales_message(notice.pk),'sent')
            self.assertEqual(deliver_sales_message(notice.pk),'duplicate');send.assert_called_once()
            second=SalesMessage.objects.create(tenant=self.tenant_a,customer=self.customer,kind='reactivation',key='second')
            self.assertEqual(deliver_sales_message(second.pk),'cooldown')

    def test_settings_isolation_validation_csrf(self):
        for body in [{'lead_minutes':-1},{'recovery_enabled':'yes'}]:
            self.assertEqual(self.client.post('/api/merchant/sales/',body,content_type='application/json').status_code,400)
        strict=Client(enforce_csrf_checks=True,HTTP_HOST=self.host(self.tenant_a));strict.force_login(self.admin_a)
        self.assertEqual(strict.post('/api/merchant/sales/',{'recovery_enabled':True},content_type='application/json').status_code,403)
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get('/api/merchant/sales/').status_code,403)

    def test_feedback_token_tenant_rating_and_unsubscribe(self):
        order=Order.objects.create(tenant=self.tenant_a,customer=self.customer,total=20,status='delivered')
        notice=self.notice('feedback',order);notice.sent_at=timezone.now();notice.save()
        url=f'/avaliacao/{notice.token}/'
        self.assertEqual(self.client.post(url,{'rating':6}).status_code,400)
        self.assertEqual(self.client.post(url,{'rating':1,'comment':'Frio'},HTTP_ACCEPT='application/json').status_code,200)
        self.client.post(url,{'rating':5},HTTP_ACCEPT='application/json')
        self.assertEqual(OrderFeedback.objects.get(order=order).rating,1)
        self.assertEqual(Client(HTTP_HOST=self.host(self.tenant_b)).get(url).status_code,404)
        self.client.post(url,{'action':'unsubscribe'},HTTP_ACCEPT='application/json')
        self.consent.refresh_from_db();self.assertFalse(self.consent.allowed)

    def test_recovery_not_planned_for_purchased_cart(self):
        Order.objects.create(tenant=self.tenant_a,customer=self.customer,total=20,source='manual',source_cart_id=self.cart.pk)
        Order.objects.filter(source_cart_id=self.cart.pk).update(created_at=self.now)
        with patch('apps.orders.sales.timezone.now',return_value=self.now),patch('apps.orders.sales.deliver_sales_message'):
            plan_sales_messages()
        self.assertFalse(SalesMessage.objects.filter(kind='recovery').exists())
