"""Package 04 regression tests. No Gemini requests and no WhatsApp sends."""
from django.test import TestCase
from apps.prospecting.commercial_smart import render
from apps.prospecting.commercial_models import CommercialArticle, CommercialConversation, CommercialMessage


class PresentationTests(TestCase):
    def setUp(self):
        self.conv = CommercialConversation.objects.create(instance='presentation-test', phone='559988887777')
        self.articles = [
            CommercialArticle.objects.create(slug='contratacao', version=1, title='Planos', published=True,
                body='O VemDeDelivery possui planos mensal, trimestral, semestral e anual. Os preços devem ser consultados exclusivamente no catálogo comercial aprovado. Não prometer gratuidade, descontos adicionais ou prazos.'),
            CommercialArticle.objects.create(slug='integracoes', version=1, title='Integrações', published=True,
                body='A plataforma possui integração de pedidos com iFood e uma implementação de integração com 99Food. A disponibilidade de cada integração depende da configuração e homologação aplicável. Não é correto afirmar que qualquer conta conecta imediatamente.'),
            CommercialArticle.objects.create(slug='pedidos', version=1, title='Pedidos', published=True,
                body='O painel operacional organiza os pedidos. A cozinha utiliza o KDS para visualizar os pedidos. Não prometer resultados garantidos.'),
        ]
        self.prices = {'data': {'plans': [
            {'name':'Mensal','months':1,'total':'149.90','discount':'0.00'},
            {'name':'Trimestral','months':3,'total':'427.22','discount':'5.00'},
            {'name':'Semestral','months':6,'total':'809.46','discount':'10.00'},
            {'name':'Anual','months':12,'total':'1528.98','discount':'15.00'},
        ]}}

    def inbound(self, text):
        CommercialMessage.objects.create(conversation=self.conv, provider_id=f'in{self.conv.messages.count()}',text=text,from_me=False)

    def choice(self, ids=None, scope='none', question='none', human=False):
        return {'article_ids':ids if ids is not None else [], 'pricing_scope':scope,'question':question,'human':human}

    def test_no_internal_policy_in_client_reply(self):
        self.inbound('integra ifood e 99food?')
        answer,_ = render(self.conv,self.prices,self.articles,self.choice([self.articles[1].pk]))
        self.assertIn('iFood',answer)
        self.assertIn('99Food',answer)
        self.assertIn('homologação aplicável',answer)
        self.assertNotIn('Não é correto afirmar',answer)

    def test_price_monthly_without_documentation(self):
        self.inbound('tenho pizzaria quanto custa?')
        answer,_ = render(self.conv,self.prices,self.articles,self.choice([self.articles[0].pk],'monthly','business'))
        self.assertIn('R$ 149,90',answer)
        self.assertNotIn('Os preços devem',answer)
        self.assertNotIn('Não prometer',answer)
        self.assertNotIn('Qual é o tipo',answer)
        self.assertIn('demonstração',answer)

    def test_annual_brazilian_format(self):
        self.inbound('quanto fica no anual?')
        answer,_=render(self.conv,self.prices,self.articles,self.choice(scope='all'))
        self.assertIn('Anual: R$ 1.528,98',answer)
        self.assertIn('15% de desconto',answer)
        self.assertNotIn('mês(es)',answer)

    def test_unanswered_business_question_kept(self):
        self.inbound('olá, quero saber sobre pedidos')
        answer,_=render(self.conv,self.prices,self.articles,self.choice([self.articles[2].pk],question='business'))
        self.assertIn('Qual é o tipo do seu estabelecimento?',answer)

    def test_previous_question_not_repeated(self):
        self.inbound('tenho pizzaria')
        previous = self.conv.messages.first()
        previous.reply='Quer que eu te mostre a demonstração do VemDeDelivery?'
        previous.save(update_fields=['reply'])
        self.inbound('e os pedidos?')
        answer,_=render(self.conv,self.prices,self.articles,self.choice([self.articles[2].pk],question='business'))
        self.assertNotIn('Quer que eu te mostre',answer)
        self.assertNotIn('Qual é o tipo',answer)
        self.assertIn('KDS',answer)

    def test_reject_human_selection(self):
        with self.assertRaises(ValueError):
            render(self.conv,self.prices,self.articles,self.choice(human=True))

    def test_no_unapproved_ai_text(self):
        self.inbound('cozinha')
        choice=self.choice([self.articles[2].pk])
        choice['answer']='O sistema é gratuito!'
        answer,_=render(self.conv,self.prices,self.articles,choice)
        self.assertNotIn('gratuito',answer)

    def test_repeated_answer_needs_human_instead_of_empty_greeting(self):
        self.inbound('como funciona o painel?')
        earlier=self.conv.messages.first()
        earlier.reply='O painel operacional organiza os pedidos. A cozinha utiliza o KDS para visualizar os pedidos.'
        earlier.save(update_fields=['reply'])
        self.inbound('e painel?')
        with self.assertRaises(ValueError):
            render(self.conv,self.prices,self.articles,self.choice([self.articles[2].pk]))

    def test_three_topics_bounded(self):
        self.inbound('quero conhecer')
        answer,_=render(self.conv,self.prices,self.articles,self.choice([a.pk for a in self.articles],scope='monthly',question='demo'))
        self.assertLessEqual(len(answer),3200)
        self.assertNotIn('Os preços devem',answer)

    def test_never_send_unsupported_fact_only(self):
        self.inbound('quero saber')
        unsafe=CommercialArticle.objects.create(slug='comissoes',version=1,title='instrucoes',published=True,body='Não prometer gratuidade. Não afirmar desconto.')
        with self.assertRaises(ValueError):
            render(self.conv,self.prices,self.articles+[unsafe],self.choice([unsafe.pk]))
