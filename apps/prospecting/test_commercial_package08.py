"""Offline regression cases. Written for local execution; no provider or WhatsApp IO."""
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import TestCase
from .commercial import articles
from .commercial_models import CommercialArticle, CommercialControl, CommercialConversation, CommercialMessage
from .commercial_smart import compose
from .management.commands.prepare_commercial_package08 import ARTICLES


class Package08Tests(TestCase):
    def setUp(self):
        self.control = CommercialControl.objects.create(enabled=False, instance='')
        self.conv = CommercialConversation.objects.create(instance='offline08', phone='5511999990000')
        self.knowledge = [CommercialArticle.objects.create(slug=s, title=t, body=b, version=1, published=True)
                          for s,t,b in ARTICLES]
        self.publication = {'fingerprint':'test', 'data':{'plans':[
            dict(name=n, months=m, total=t, discount=d) for n,m,t,d in (
                ('Mensal',1,'149.90',0), ('Trimestral',3,'427.22',5),
                ('Semestral',6,'809.46',10), ('Anual',12,'1528.98',15))]}}

    def answer(self, text, *, slugs=(), scope='none', question='none', human=False):
        self.conv.messages.all().delete()
        CommercialMessage.objects.create(conversation=self.conv, provider_id='08', text=text)
        choice = dict(article_ids=[a.pk for a in self.knowledge if a.slug in slugs],
                      pricing_scope=scope, question=question, human=human)
        with patch('apps.prospecting.commercial_smart.classify', return_value=choice):
            return compose(self.conv, self.publication, self.knowledge)[0]

    def test_019_044_054_079_review_before_classifier(self):
        for text in ('gera site, atende zap, faz cardapio e entrega motoboy?',
                     'qual impressora térmica vocês homologaram?',
                     'agente recebe pedido de áudio e transcreve?',
                     'faz sistema para clínica e agendamento médico?',
                     'funciona com minha impressora Bluetooth?'):
            with self.subTest(text=text):
                self.conv.messages.all().delete()
                CommercialMessage.objects.create(conversation=self.conv, provider_id='08', text=text)
                with patch('apps.prospecting.commercial_smart.classify') as classifier:
                    with self.assertRaisesRegex(ValueError, 'commercial_human_review_required'):
                        compose(self.conv, self.publication, self.knowledge)
                    classifier.assert_not_called()

    def test_091_092_093_published_objections(self):
        for text, words in (
            ('149,90 é caro, por que vale a pena?', ('tarefas', 'não há garantia')),
            ('já tenho cardápio no Instagram, pra que outro?', ('complementa', 'pedidos diretos')),
            ('eu só vendo por iFood, isso me ajuda?', ('pedidos diretos', 'liberação')),
        ):
            with self.subTest(text=text):
                result = self.answer(text)
                self.assertLessEqual(len(result), 500)
                for word in words:
                    self.assertIn(word, result)
                self.assertNotIn('garantia de aumento', result)
                self.assertNotIn('R$', result)

    def test_missing_objection_not_replaced_by_generic_sales_copy(self):
        self.knowledge = [a for a in self.knowledge if a.slug != 'objecao-valor']
        with self.assertRaisesRegex(ValueError, 'commercial_topics_uncovered'):
            self.answer('149,90 é caro, por que vale a pena?', slugs=('pedidos',))

    def test_094_with_and_without_approved_link(self):
        with self.assertRaisesRegex(ValueError, 'commercial_demo_human_required'):
            self.answer('posso ver uma demonstração?', question='demo')
        self.control.demo_url = 'https://demo.example.com/'
        self.control.save()
        result = self.answer('posso ver uma demonstração?', question='demo')
        self.assertIn(self.control.demo_url, result)
        self.assertNotIn('?', result)

    def test_demo_cannot_use_article_or_model_url(self):
        article = self.knowledge[0]
        article.body = 'Visite https://inventado.example.com para conhecer.'
        article.save()
        with self.assertRaises(ValueError):
            self.answer('posso ver uma demonstração?', slugs=('pedidos',))

    def test_three_questions_complete_and_short_without_unrelated_topics(self):
        result = self.answer('Sou pizzaria, qual valor, tem cozinha e imprime?',
                             slugs=('pedidos','impressao','whatsapp','integracoes'), question='business')
        for word in ('149,90','KDS','impressão','compatibilidade','antecipado'):
            self.assertIn(word, result)
        self.assertLessEqual(len(result), 500)
        self.assertNotIn('WhatsApp',result)
        self.assertNotIn('iFood',result)
        self.assertNotIn('tipo do seu estabelecimento',result)
        self.assertLessEqual(result.count('?'),1)

    def test_direct_questions(self):
        for question, facts in (
            ('O que é KDS?', ('tela da cozinha', 'preparo')),
            ('O site funciona no celular?', ('Sim', 'celular', 'navegador')),
            ('Tem entrega e retirada?', ('configurar entrega e retirada', 'não fornece motoboys')),
            ('O agente entende erros de português?', ('abreviações', 'não é perfeita')),
            ('Funciona com impressora térmica?', ('compatibilidade',)),
        ):
            with self.subTest(question=question):
                result = self.answer(question)
                for fact in facts:
                    self.assertIn(fact, result)
                self.assertLessEqual(len(result),300)

    def test_catalog_prices_and_periods_preserved(self):
        result = self.answer('quais são os planos?')
        for value in ('149,90','427,22','809,46','1.528,98','5%','10%','15%'):
            self.assertIn(value, result)
        self.publication['data']['plans'][0]['total'] = '159.90'
        result = self.answer('quanto custa por mês?')
        self.assertIn('159,90',result)
        self.assertNotIn('149,90',result)

    def test_price_not_repeated_for_nonprice_question(self):
        result = self.answer('tem cozinha?', scope='monthly')
        self.assertNotIn('R$',result)

    def test_human_decision_preserved(self):
        with self.assertRaisesRegex(ValueError, 'human_review_required'):
            self.answer('tem cozinha?', human=True)

    def test_embedded_questions_removed_and_one_contextual_cta(self):
        article = next(a for a in self.knowledge if a.slug == 'pedidos')
        article.body += ' Qual parte quer melhorar? Quer conhecer?'
        result = self.answer('tem cozinha?',question='pain')
        self.assertEqual(result.count('?'),1)
        self.assertIn('maior dificuldade',result)

    def test_no_truncation_of_safety_conditions(self):
        article = next(a for a in self.knowledge if a.slug == 'impressao')
        article.body = ('A impressão exige validar o equipamento e configurar o computador. ' * 13).strip()
        answer = self.answer('imprime?')
        self.assertEqual(answer, 'A impressão exige validar o equipamento e configurar o computador.')

    def test_preparation_preserves_publication_and_creates_only_drafts(self):
        latest = self.knowledge[0]
        latest.body = 'Texto personalizado publicado.'
        latest.save()
        before = list(CommercialArticle.objects.values_list('pk','body','published'))
        call_command('prepare_commercial_package08', stdout=StringIO())
        call_command('prepare_commercial_package08', apply=True, stdout=StringIO())
        self.assertEqual(before,list(CommercialArticle.objects.values_list('pk','body','published')))
        call_command('prepare_commercial_package08', apply=True, revise_existing=True, stdout=StringIO())
        draft = CommercialArticle.objects.get(slug=latest.slug,version=2)
        self.assertFalse(draft.published)
        self.assertNotIn(latest.slug,{a.slug for a in articles()})
        count = CommercialArticle.objects.count()
        call_command('prepare_commercial_package08', apply=True, revise_existing=True, stdout=StringIO())
        self.assertEqual(count,CommercialArticle.objects.count())
        self.control.refresh_from_db()
        self.assertFalse(self.control.enabled)
        self.assertEqual(self.control.instance,'')

    def test_battery_metadata_tracks_demo_configuration(self):
        from .commercial_battery import metadata
        before = metadata(self.publication,self.knowledge)
        self.control.demo_url = 'https://demo.example.com/'
        self.control.save()
        after = metadata(self.publication,self.knowledge)
        self.assertFalse(before['demo_configured'])
        self.assertTrue(after['demo_configured'])
        self.assertNotEqual(before['commercial_links_sha256'],after['commercial_links_sha256'])
