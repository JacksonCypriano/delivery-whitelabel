"""No real Gemini, Redis or WhatsApp calls: deterministic deferral coverage."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from apps.billing.models import Plan
from .commercial_catalog import catalog
from .commercial_models import CommercialControl, CommercialMessage, CommercialConversation, CommercialArticle
from .commercial_quota import CommercialQuotaDeferred
from .commercial import process_message


@override_settings(COMMERCIAL_AGENT_ENABLED=True)
class CommercialQuotaQueueTests(TestCase):
    def setUp(self):
        self.control=CommercialControl.objects.create(instance='quota-test',enabled=True)
        for months,discount in [(1,0),(3,5),(6,10),(12,15)]:
            Plan.objects.update_or_create(months=months,defaults={'name':str(months),'monthly_price':'149.90','discount':discount,'active':True})
        self.control.catalog_fingerprint=catalog()['fingerprint']
        self.control.save()
        CommercialArticle.objects.create(slug='pedidos',version=1,title='Pedidos',body='Organiza os pedidos.',published=True)
        self.conv=CommercialConversation.objects.create(instance='quota-test',phone='5511999999888')
        self.row=CommercialMessage.objects.create(conversation=self.conv,provider_id='quota-test-1',text='quanto custa?',state='queued')

    def test_quota_exhaustion_defers_without_human_or_send(self):
        with patch('apps.prospecting.commercial.TenantEvolutionClient') as client, patch('apps.prospecting.commercial.compose',side_effect=CommercialQuotaDeferred(65,'commercial_quota_wait')):
            client.return_value.status.return_value='open'
            process_message(self.row.pk)
            client.return_value.send_text.assert_not_called()
        self.row.refresh_from_db()
        self.conv.refresh_from_db()
        self.assertEqual(self.row.state,'queued')
        self.assertGreater(self.row.next_attempt_at,timezone.now()+timedelta(seconds=50))
        self.assertFalse(self.conv.paused)

    def test_not_due_does_not_touch_provider(self):
        self.row.next_attempt_at=timezone.now()+timedelta(minutes=5)
        self.row.save(update_fields=['next_attempt_at'])
        with patch('apps.prospecting.commercial.TenantEvolutionClient') as client:
            process_message(self.row.pk)
            client.assert_not_called()


class QuotaAtomicTests(TestCase):
    @override_settings(COMMERCIAL_GEMINI_RPM=8,COMMERCIAL_GEMINI_RPD=350)
    @patch('apps.prospecting.commercial_quota._redis')
    def test_reserve_defers_when_shared_minute_is_full(self, redis):
        from .commercial_quota import reserve
        redis.return_value.eval.return_value=[0,42,8,20]
        with self.assertRaises(CommercialQuotaDeferred) as raised:
            reserve('gemini-3.5-flash-lite',now=1730912345)
        self.assertEqual(raised.exception.seconds,42)

    @override_settings(COMMERCIAL_GEMINI_RPM=8,COMMERCIAL_GEMINI_RPD=350)
    @patch('apps.prospecting.commercial_quota._redis')
    def test_reserve_succeeds_and_uses_atomic_eval(self, redis):
        from .commercial_quota import reserve
        redis.return_value.eval.return_value=[1,0,2,12]
        self.assertIsNone(reserve('gemini-3.5-flash-lite',now=1730912345))
        self.assertEqual(redis.return_value.eval.call_count,1)
