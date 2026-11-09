"""Smart mode: semantic classification is mocked; never sends real WhatsApp messages."""
import json
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from apps.billing.models import Plan
from .commercial_smart import compose  # Archived provider contract; operational entrypoint is tested separately.
from .commercial_catalog import catalog
from .commercial_models import CommercialArticle, CommercialConversation, CommercialMessage
from .commercial_smart import render, redact


@override_settings(COMMERCIAL_AGENT_MODE='smart',COMMERCIAL_AGENT_GEMINI_API_KEY='test-key')
class SmartCommercialTests(TestCase):
    def setUp(self):
        quota_patch = patch('apps.prospecting.commercial_smart.reserve')
        quota_patch.start()
        self.addCleanup(quota_patch.stop)
        for months, discount in ((1,0),(3,5),(6,10),(12,15)):
            Plan.objects.update_or_create(months=months, defaults={'name':f'Plano {months}','monthly_price':'149.90','discount':discount,'active':True})
        self.articles=[]
        for slug, body in [('pedidos','O painel organiza os pedidos e a cozinha.'),
                          ('integracoes','O VemDeDelivery integra pedidos dos canais homologados.'),
                          ('whatsapp','O atendimento WhatsApp é integrado ao painel.')]:
            self.articles.append(CommercialArticle.objects.create(slug=slug,title=slug,body=body,version=1,published=True))
        self.conv=CommercialConversation.objects.create(instance='smart-test',phone='5511999999000')
        self.inbound('tenho uma pizzaria e queria saber preço, ifood e cozinha')

    def inbound(self,text):
        return CommercialMessage.objects.create(conversation=self.conv,provider_id=f'in-{self.conv.messages.count()}',text=text)

    def choice(self,**overrides):
        choice={'article_ids':[x.pk for x in self.articles[:2]],'pricing_scope':'monthly','question':'demo','human':False}
        choice.update(overrides)
        return choice

    def test_smart_answers_three_topics_and_official_monthly(self):
        selected=self.choice()
        with patch('apps.prospecting.commercial_smart.classify',return_value=selected):
            answer,ids=compose(self.conv,catalog(),self.articles)
        self.assertEqual(ids,selected['article_ids'])
        self.assertIn('149,90',answer)
        self.assertIn('cozinha',answer)
        self.assertIn('canais homologados',answer)
        self.assertNotIn('Plano 12:',answer)

    def test_model_cannot_expand_monthly_question_to_full_plans(self):
        answer,_=render(self.conv,catalog(),self.articles,self.choice(pricing_scope='all'))
        self.assertNotIn('Plano 12:',answer)
        self.assertIn('Plano 1:',answer)

    def test_unknown_article_rejected(self):
        with self.assertRaises(ValueError):render(self.conv,catalog(),self.articles,self.choice(article_ids=[999]))

    def test_four_articles_rejected(self):
        with self.assertRaises(ValueError):render(self.conv,catalog(),self.articles,self.choice(article_ids=[1,2,3,4]))

    def test_duplicate_article_deduplicated_and_coverage_repaired(self):
        answer, ids = render(self.conv,catalog(),self.articles,self.choice(article_ids=[self.articles[0].pk]*2))
        self.assertEqual(ids, [a.pk for a in self.articles[:2]])
        self.assertEqual(answer.count(self.articles[0].body), 1)

    def test_human_handoff(self):
        with self.assertRaises(ValueError):render(self.conv,catalog(),self.articles,self.choice(human=True))

    def test_invalid_pricing_scope_rejected(self):
        with self.assertRaises(ValueError):render(self.conv,catalog(),self.articles,self.choice(pricing_scope='free'))

    def test_no_ai_generated_response_used(self):
        answer,_=render(self.conv,catalog(),self.articles,self.choice(answer='Tudo grátis, garantido!'))
        self.assertNotIn('Tudo grátis',answer)

    def test_repeated_article_not_resent(self):
        previous=self.inbound('mais info')
        previous.reply=self.articles[0].body
        previous.save()
        answer,_=render(self.conv,catalog(),self.articles,self.choice(article_ids=[x.pk for x in self.articles]))
        self.assertEqual(answer.count(self.articles[0].body),0)

    def test_redaction(self):
        result=redact('Meu e-mail é exemplo@dominio.com e número +55 (11) 99999-0000 https://teste.com')
        self.assertNotIn('exemplo@dominio.com',result)
        self.assertNotIn('99999',result)
        self.assertNotIn('https://',result)

    def test_not_call_provider_without_key(self):
        with override_settings(COMMERCIAL_AGENT_GEMINI_API_KEY=''):
            with patch('apps.prospecting.commercial_smart.requests.Session') as session:
                with self.assertRaises(ValueError):compose(self.conv,catalog(),self.articles)
                session.assert_not_called()

    def test_provider_failure_no_rules_fallback(self):
        from .commercial_quota import CommercialQuotaDeferred
        response=Mock(status_code=503,content=b'{}')
        with patch('apps.prospecting.commercial_smart.time.sleep'), patch('apps.prospecting.commercial_smart.requests.Session') as s:
            post=s.return_value.__enter__.return_value.post
            post.return_value=response
            with self.assertRaisesRegex(CommercialQuotaDeferred, 'smart_provider_http_503'):
                compose(self.conv,catalog(),self.articles)
            self.assertEqual(post.call_count, 2)

    def test_provider_payload_has_no_phone(self):
        response=Mock(status_code=200, content=b'{}')
        response.json.return_value={'candidates':[{'content':{'parts':[{'text':json.dumps(self.choice())}]}}]}
        with patch('apps.prospecting.commercial_smart.requests.Session') as s:
            s.return_value.__enter__.return_value.post.return_value=response
            compose(self.conv,catalog(),self.articles)
            payload=s.return_value.__enter__.return_value.post.call_args.kwargs['json']
        self.assertNotIn(self.conv.phone,json.dumps(payload))
