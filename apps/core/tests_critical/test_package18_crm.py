from datetime import timedelta
from decimal import Decimal
import uuid
from django.test import Client
from django.utils import timezone
from apps.customers.models import Customer
from apps.orders.models import Order,LoyaltySettings,LoyaltyEntry,CustomerCampaign,MarketingConsent,SalesMessage,FunnelEvent
from apps.orders.crm import accrue_loyalty,redeem,customers,plan_customer_campaigns
from .base import CriticalTestCase

class CRMTests(CriticalTestCase):
    def setUp(self):
        self.customer=Customer.objects.create(user=self.admin_a,phone='11976543210',phone_verified=True)
        self.cfg=LoyaltySettings.objects.create(tenant=self.tenant_a,enabled=True,enabled_at=timezone.now()-timedelta(days=1),reward_points=10,reward_value=5)
        self.order=Order.objects.create(tenant=self.tenant_a,customer=self.customer,source='manual',status='delivered',total=25)
        self.client=Client(HTTP_HOST=self.host(self.tenant_a));self.client.force_login(self.admin_a)

    def test_award_and_redeem_are_idempotent(self):
        accrue_loyalty();accrue_loyalty();self.assertEqual(LoyaltyEntry.objects.count(),1)
        key=str(uuid.uuid4());coupon=redeem(self.tenant_a,self.customer.pk,key)
        self.assertEqual(redeem(self.tenant_a,self.customer.pk,key).pk,coupon.pk)
        self.assertEqual(LoyaltyEntry.objects.count(),2)
        self.assertTrue(coupon.assignments.filter(customer=self.customer).exists())
        self.order.refresh_from_db();self.assertEqual(self.order.total,Decimal(25))

    def test_insufficient_points_and_cross_tenant(self):
        with self.assertRaises(ValueError):redeem(self.tenant_a,self.customer.pk,str(uuid.uuid4()))
        accrue_loyalty()
        with self.assertRaises(ValueError):redeem(self.tenant_b,self.customer.pk,str(uuid.uuid4()))
        self.assertEqual(customers(self.tenant_b),[])

    def test_unpaid_online_order_not_rewarded(self):
        self.order.payment_flow='online';self.order.save()
        accrue_loyalty();self.assertEqual(LoyaltyEntry.objects.count(),0)

    def test_campaign_only_opted_in_segment_and_once(self):
        c=CustomerCampaign.objects.create(tenant=self.tenant_a,name='Novos',segment='new',text='Olá',active=True)
        plan_customer_campaigns();self.assertFalse(SalesMessage.objects.exists())
        MarketingConsent.objects.create(tenant=self.tenant_a,customer=self.customer,allowed=True)
        plan_customer_campaigns();plan_customer_campaigns()
        self.assertEqual(SalesMessage.objects.filter(campaign=c).count(),1)

    def test_public_funnel_rejects_purchase_and_requires_consent(self):
        url='/eventos/loja/'
        self.assertEqual(self.client.post(url,{'stage':'visit'},content_type='application/json').status_code,400)
        self.assertEqual(self.client.post(url,{'stage':'payment','consent':True},content_type='application/json').status_code,400)
        for _ in range(2):self.assertEqual(self.client.post(url,{'stage':'visit','consent':True},content_type='application/json').status_code,200)
        self.assertEqual(FunnelEvent.objects.count(),1)

    def test_crm_profile_other_tenant_denied(self):
        other=Customer.objects.create(user=self.admin_b,phone='11911112222')
        self.assertEqual(self.client.post('/api/merchant/crm/',{'action':'profile','customer':other.pk,'notes':'x'},content_type='application/json').status_code,400)
        response=self.client.get('/api/merchant/crm/')
        self.assertEqual(response.status_code,200)
        self.assertEqual([c['id'] for c in response.json()['customers']],[self.customer.pk])
