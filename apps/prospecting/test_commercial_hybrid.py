"""Tests for commercial agent without Ollama, and safeguarded Gemini fallback."""
import json
from unittest.mock import patch, Mock
from django.test import TestCase, override_settings
from apps.billing.models import Plan
from .commercial_catalog import catalog
from .commercial_models import CommercialArticle, CommercialControl, CommercialConversation, CommercialMessage
from .commercial import compose


class HybridCommercialTests(TestCase):
    def setUp(self):
        self.control = CommercialControl.objects.create(instance='hybrid-test', enabled=False)
        for months, discount in [(1, 0), (3, 5), (6, 10), (12, 15)]:
            Plan.objects.update_or_create(months=months, defaults={'name': str(months), 'monthly_price': '149.90', 'discount': discount, 'active': True})
        self.article = CommercialArticle.objects.create(slug='pedidos', title='Pedidos', body='O painel organiza os pedidos e a cozinha.', published=True, version=1)
        self.conv = CommercialConversation.objects.create(instance='hybrid-test', phone='5511999999000')

    def inbound(self, text):
        CommercialMessage.objects.create(conversation=self.conv, provider_id=f'in-{self.conv.messages.count()}', text=text)
        return catalog()

    @override_settings(COMMERCIAL_AGENT_MODE='rules')
    def test_answer_without_llm(self):
        data = self.inbound('Como funciona a cozinha e os pedidos?')
        with patch('apps.prospecting.commercial.requests.Session') as session:
            answer, ids = compose(self.conv, data, [self.article])
            session.assert_not_called()
        self.assertIn('organiza os pedidos', answer)
        self.assertEqual(ids, [self.article.pk])

    @override_settings(COMMERCIAL_AGENT_MODE='rules')
    def test_unknown_topic_does_not_hallucinate(self):
        data = self.inbound('Vocês vendem helicópteros?')
        with self.assertRaises(ValueError):
            compose(self.conv, data, [self.article])

    @override_settings(COMMERCIAL_AGENT_MODE='rules')
    def test_price_must_use_official_catalog(self):
        data = self.inbound('Qual o preço e desconto dos planos?')
        answer, _ = compose(self.conv, data, [self.article])
        self.assertIn('149,90', answer)

    @override_settings(COMMERCIAL_AGENT_MODE='hybrid', COMMERCIAL_AGENT_GEMINI_API_KEY='test-key')
    def test_gemini_bad_article_id_falls_back_to_rules(self):
        data = self.inbound('Como funciona a cozinha?')
        response = Mock(status_code=200, content=b'{}')
        response.json.return_value = {'candidates': [{'content': {'parts': [{'text': json.dumps({'article_ids':[99999], 'pricing':False, 'question':'none', 'human':False})}]}}]}
        with patch('apps.prospecting.commercial.requests.Session') as session:
            session.return_value.__enter__.return_value.post.return_value = response
            answer, ids = compose(self.conv, data, [self.article])
        self.assertIn('pedidos', answer)
        self.assertEqual(ids, [self.article.pk])

    @override_settings(COMMERCIAL_AGENT_MODE='hybrid', COMMERCIAL_AGENT_GEMINI_API_KEY='')
    def test_hybrid_without_key_uses_rules(self):
        data = self.inbound('Quero entender os pedidos')
        with patch('apps.prospecting.commercial.requests.Session') as session:
            answer, ids = compose(self.conv, data, [self.article])
            session.assert_not_called()
        self.assertTrue(ids)
