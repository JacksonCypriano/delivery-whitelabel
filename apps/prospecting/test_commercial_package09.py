"""Package 09 regressions, written but not executed during delivery.

Long public excerpts are from the complete battery 08 report, not replacement
production knowledge. Classifier mocked; no network, provider or DB writes.
"""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from .commercial_battery import conversation
from .commercial_smart import compose

BODIES = {'visao-geral': 'O VemDeDelivery é uma plataforma para restaurantes, pizzarias, hamburguerias, marmitarias, açaiterias e outros estabelecimentos. Reúne cardápio digital próprio, pedidos online, atendimento por WhatsApp, organização da cozinha, entregas, retiradas e gestão comercial. Ajuda o estabelecimento a organizar sua operação e desenvolver vendas diretas. Não somos uma transportadora nem fornecemos entregadores próprios. Os resultados dependem da rotina e da utilização da plataforma.', 'pedidos': 'O painel operacional organiza pedidos do cardápio próprio e dos canais integrados que estiverem habilitados. Os pedidos possuem identificação de origem e acompanhamento de etapas, incluindo confirmação, preparo, pronto, retirada ou entrega conforme o fluxo. A cozinha utiliza o KDS para visualizar pedidos e acompanhar o preparo. O painel ajuda a equipe a trabalhar com informações centralizadas. A disponibilidade de operações automáticas depende da configuração do canal.', 'impressao': 'O VemDeDelivery possui recursos para impressão de comprovantes de pedidos, cozinha e entrega. Os documentos podem apresentar itens, observações, pagamento e informações operacionais do pedido. A impressão direta depende da configuração do agente de impressão e da compatibilidade do equipamento. A compatibilidade de uma impressora específica precisa ser verificada. Comprovante de pedido não deve ser confundido com nota fiscal.', 'integracoes': 'A plataforma possui integração de pedidos com iFood e uma implementação de integração com 99Food. A proposta é acompanhar pedidos de diferentes canais em uma central operacional, com identificação de origem. A disponibilidade de cada integração depende da conexão, das permissões, da configuração e da homologação aplicável.', 'kds': 'KDS é a tela da cozinha para acompanhar os pedidos e suas etapas de preparo.'}

class Package09Tests(TestCase):
    def setUp(self):
        self.knowledge = [SimpleNamespace(pk=i, slug=slug, body=body, title=slug)
                          for i, (slug, body) in enumerate(BODIES.items(), 1)]
        self.publication = {'data': {'plans': [dict(name='Mensal', months=1,
                                                   total='159.90', discount=0)]}}

    def answer(self, message, slugs=None, question='business', human=False):
        self.conv = conversation({'messages': message})
        selection = dict(article_ids=[a.pk for a in self.knowledge
                                     if slugs is None or a.slug in slugs],
                         pricing_scope='none', question=question, human=human)
        with patch('apps.prospecting.commercial_smart.classify', return_value=selection):
            return compose(self.conv, self.publication, self.knowledge)

    def test_011_price_kitchen_and_print_with_long_published_articles(self):
        answer, sources = self.answer('sou pizzaria, qual valor, tem cozinha e imprime?')
        self.assertTrue(answer.startswith('Mensal: R$ 159,90'))
        for fact in ('antecipado', 'KDS', 'impressão', 'agente de impressão',
                     'compatibilidade', 'precisa ser verificada', 'nota fiscal'):
            self.assertIn(fact, answer)
        self.assertLessEqual(len(answer), 800)
        self.assertNotIn('tipo do seu estabelecimento', answer)
        self.assertNotIn('iFood', answer)
        self.assertIn(next(a.pk for a in self.knowledge if a.slug == 'kds'), sources)

    def test_023_informal_printing_retains_complete_equipment_conditions(self):
        answer, _ = self.answer('da pra impremir pedidu da cozina?')
        self.assertIn(BODIES['impressao'], answer)
        self.assertLessEqual(len(answer), 800)

    def test_028_business_already_known(self):
        answer, _ = self.answer('mnh loja vende acai e lanxe da pra usar?')
        self.assertIn('açaiterias', answer)
        self.assertNotIn('tipo do seu estabelecimento', answer)
        self.assertLessEqual(len(answer), 800)

    def test_039_differences_are_published_facts(self):
        answer, sources = self.answer('qq cê faz de diferente do app de delivery?', question='none')
        self.assertEqual(answer, BODIES['visao-geral'])
        self.assertEqual(sources, [next(a.pk for a in self.knowledge if a.slug == 'visao-geral')])

    def test_061_sequential_context_and_catalog_price_without_sales_pitch(self):
        answer, sources = self.answer('tenho uma pizzaria | quanto custa pra mim?')
        self.assertEqual(answer, 'Mensal: R$ 159,90 por mês, com pagamento antecipado.')
        self.assertEqual(sources, [])

    def test_guarantees_never_reach_classifier(self):
        for message in ('tenho direito garantido de 100% de aumento nas vendas?',
                        'vocês garantem mais vendas?', 'aumento de vendas com garantia?',
                        'receita garantida de 30% a mais?', 'prometem dobrar meu faturamento?',
                        'vai funcionar 100% do tempo?'):
            with self.subTest(message=message):
                conv = conversation({'messages': message})
                with patch('apps.prospecting.commercial_smart.classify') as classifier:
                    with self.assertRaisesRegex(ValueError, 'commercial_human_review_required'):
                        compose(conv, self.publication, self.knowledge)
                    classifier.assert_not_called()

    def test_possible_benefits_do_not_trigger_guarantee_guard(self):
        answer, _ = self.answer('como pode ajudar minhas vendas?', slugs=('visao-geral',), question='none')
        self.assertIn('resultados dependem', answer)

    def test_kds_specific_published_article(self):
        answer, _ = self.answer('q é kds?', slugs=('pedidos',), question='none')
        self.assertEqual(answer, BODIES['kds'])
        self.knowledge = [a for a in self.knowledge if a.slug != 'kds']
        answer, _ = self.answer('q é kds?', slugs=('pedidos',), question='none')
        self.assertEqual(answer, BODIES['pedidos'])

    def test_missing_print_article_and_human_classification_fail_closed(self):
        self.knowledge = [a for a in self.knowledge if a.slug != 'impressao']
        with self.assertRaisesRegex(ValueError, 'commercial_topics_uncovered'):
            self.answer('tem cozinha e imprime?')
        with self.assertRaisesRegex(ValueError, 'human_review_required'):
            self.answer('tem cozinha?', human=True)

    def test_explicit_question_can_repeat_an_answer_without_repeating_cta(self):
        conv = conversation({'messages': 'quanto custa? | quanto custa?'})
        conv.messages[0]['reply'] = 'Mensal: R$ 159,90 por mês, com pagamento antecipado.'
        selection = dict(article_ids=[], pricing_scope='monthly', question='none', human=False)
        with patch('apps.prospecting.commercial_smart.classify', return_value=selection):
            answer, _ = compose(conv, self.publication, self.knowledge)
        self.assertEqual(answer, conv.messages[0]['reply'])
