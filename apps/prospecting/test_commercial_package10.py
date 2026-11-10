"""Offline architectural regressions. Classifier mocked; no provider/WhatsApp IO.

Not executed during package delivery. Original battery expectations are intact.
"""
import itertools
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from .commercial_battery import conversation
from .commercial_context import conversation_context
from .commercial_facts import fact_catalog
from .commercial_plan import build_plan
from .commercial_smart import compose
from .management.commands.prepare_commercial_knowledge import ARTICLES
from .management.commands.prepare_commercial_package07 import ARTICLES as OBJECTIONS
from .management.commands.prepare_commercial_package08 import ARTICLES as SHORT
from .test_commercial_package09 import BODIES


class Package10Tests(TestCase):
    def setUp(self):
        bodies = {s: b for s, _, b in (*ARTICLES, *OBJECTIONS, *SHORT)}
        bodies.update(BODIES)
        bodies['gestao'] = (
            'A loja pode configurar produtos, categorias, adicionais e pizzas meio a meio. '
            'As funcionalidades dependem das permissões e configurações da loja.')
        self.knowledge = [SimpleNamespace(pk=i, slug=s, title=s, body=b, version=3)
                          for i, (s, b) in enumerate(bodies.items(), 1)]
        self.publication = {'data': {'plans': [
            dict(name='Mensal', months=1, total='159.90', discount=0),
            dict(name='Anual', months=12, total='1629.00', discount=15)]}}
        self.classifier = patch('apps.prospecting.commercial_smart.classify').start()
        self.addCleanup(patch.stopall)

    def article(self, slug):
        return next(a for a in self.knowledge if a.slug == slug)

    def selection(self, *slugs, **kwargs):
        result = dict(article_ids=[self.article(s).pk for s in slugs],
                      pricing_scope='none', question='none', human=False)
        result.update(kwargs)
        return result

    def answer(self, message, choice=None, conv=None):
        self.classifier.return_value = choice if choice is not None else self.selection()
        return compose(conv or conversation({'messages': message}), self.publication, self.knowledge)

    def semantic(self, intent, evidence, indices=(0,)):
        facts = fact_catalog(self.knowledge).get(intent, ())
        return dict(intent=intent, evidence=evidence, fact_ids=[facts[i].key for i in indices])

    def test_six_package09_divergences_with_duplicate_irrelevant_hints(self):
        cases = (
            ('o que oferece? quanto custa? tem comissão?', ('plataforma', '159,90', 'comissão', 'independentes')),
            ('faz entreaga e retiraada tbm?', ('entrega e retirada', 'não fornece motoboys')),
            ('tem kanban da cozinha com pedidos novos e prontos?', ('painel operacional', 'etapas', 'KDS')),
            ('tem atendimento automatizado e cardápio com adicionais?', ('WhatsApp', 'adicionais', 'permissões')),
            ('149,90 é caro, por que vale a pena?', ('tarefas', 'não há garantia')),
            ('eu só vendo por iFood, isso me ajuda?', ('pedidos diretos', 'liberação')),
        )
        for message, expected in cases:
            with self.subTest(message=message):
                choice = self.selection('integracoes', 'integracoes', 'impressao')
                answer, ids = self.answer(message, choice)
                for word in expected:
                    self.assertIn(word, answer)
                self.assertEqual(len(ids), len(set(ids)))
                self.assertNotIn('garantimos', answer)
                if 'quanto' not in message:
                    self.assertNotIn('R$', answer)

    def test_permutation_of_articles_and_hints_preserves_answer_and_sources(self):
        base = list(self.knowledge)
        answers = []
        for slugs in itertools.permutations(('pedidos', 'impressao', 'integracoes')):
            self.knowledge = list(reversed(self.knowledge))
            answers.append(self.answer('sou pizzaria qual valor tem cozinha e imprime?', self.selection(*slugs)))
        self.assertTrue(all(answer == answers[0] for answer in answers))
        self.knowledge = base
        self.assertNotIn('iFood', answers[0][0])

    def test_more_than_six_covered_questions_do_not_hit_article_limit(self):
        message = 'tem cardapio zap cozinha imprime integra ifood comissao celular e vale a pena?'
        answer, ids = self.answer(message)
        for fact in ('WhatsApp', 'KDS', 'impressão', 'iFood', 'comissão', 'celular'):
            self.assertIn(fact, answer)
        self.assertGreaterEqual(len(ids), 7)
        self.assertIn('homologação', answer)

    def test_semantic_fragments_and_required_conditions(self):
        message = 'uso ifood | tem impressão? | e cozinha?'
        choice = self.selection('integracoes', questions=[
            self.semantic('impressao', 'tem impressão?'),
            self.semantic('kds', 'e cozinha?'),
        ])
        answer, ids = self.answer(message, choice)
        self.assertIn('impressão', answer)
        self.assertIn('compatibilidade', answer)
        self.assertIn('nota fiscal', answer)
        self.assertIn('KDS', answer)
        self.assertNotIn('iFood', answer)
        self.assertNotIn(self.article('integracoes').pk, ids)

    def test_new_paraphrase_uses_semantic_intent_and_verbatim_fact(self):
        message = 'dá para a turma acompanhar o que está sendo feito no fogão?'
        answer, _ = self.answer(message, self.selection(questions=[self.semantic('kds', message)]))
        self.assertEqual(answer, self.article('kds').body)

    def test_multi_question_evidence_cannot_hide_recognized_missing_topic(self):
        message = 'tem cozinha e imprime?'
        answer, _ = self.answer(message, self.selection(questions=[self.semantic('kds', message)]))
        self.assertIn('KDS', answer)
        self.assertIn('impressão', answer)
        self.assertIn('compatibilidade', answer)

    def test_missing_knowledge_and_unsupported_semantic_question_are_not_invented(self):
        self.knowledge = [a for a in self.knowledge if a.slug != 'impressao']
        with self.assertRaisesRegex(ValueError, 'commercial_topics_uncovered'):
            self.answer('tem cozinha e imprime?')
        choice = self.selection(questions=[dict(intent='unsupported', evidence='faz isso?', fact_ids=[])])
        with self.assertRaisesRegex(ValueError, 'commercial_topics_uncovered'):
            self.answer('faz isso?', choice)

    def test_explicit_human_and_safety_guards_are_not_repaired(self):
        with self.assertRaisesRegex(ValueError, 'human_review_required'):
            self.answer('tem cozinha?', self.selection(human=True))
        self.classifier.reset_mock()
        for message in ('garantem mais vendas?', 'quero falar com uma pessoa',
                        'qual impressora homologada?', 'transcreve áudio?',
                        'sistema para clínica médica?', 'fornecem motoboy?'):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, 'commercial_human_review_required'):
                self.answer(message)
        self.classifier.assert_not_called()

    def test_feature_question_about_human_support_does_not_request_handoff(self):
        answer, _ = self.answer('o atendente humano consegue assumir a conversa?')
        self.assertIn('assumir', answer)

    def test_unknown_ids_wrong_fact_source_and_invalid_evidence_fail_closed(self):
        for choice in (
            self.selection(article_ids=[999999]),
            self.selection(article_ids=[True]),
            self.selection(questions=[dict(intent='kds', evidence='tem cozinha?', fact_ids=['999:0'])]),
            self.selection(questions=[self.semantic('kds', 'texto que não foi enviado')]),
            self.selection(questions='invalid'),
        ):
            with self.subTest(choice=choice), self.assertRaises(ValueError):
                self.answer('tem cozinha?', choice)

    def test_model_prose_prices_and_urls_are_never_rendered(self):
        answer, _ = self.answer('quanto custa?', self.selection(answer='R$ 1 grátis https://evil.example', pricing_scope='all'))
        self.assertEqual(answer, 'Mensal: R$ 159,90 por mês, com pagamento antecipado.')
        self.assertNotIn('evil', answer)

    def test_long_safe_fact_is_not_handed_off_or_truncated(self):
        article = self.article('kds')
        article.body = 'KDS acompanha ' + 'pedidos e etapas ' * 70 + 'conforme configuração.'
        answer, _ = self.answer('o que é kds?')
        self.assertEqual(answer, article.body)
        self.assertTrue(answer.endswith('conforme configuração.'))

    def test_repeated_sentences_are_deduplicated_without_dropping_conditions(self):
        article = self.article('impressao')
        article.body = 'Há impressão de pedidos. A compatibilidade precisa ser verificada. ' * 20
        answer, _ = self.answer('imprime?')
        self.assertEqual(answer.count('Há impressão'), 1)
        self.assertEqual(answer.count('compatibilidade'), 1)

    def test_explicit_repeat_is_answered_without_repeated_qualification(self):
        conv = conversation({'messages': 'o que é KDS? | o que é KDS?'})
        conv.messages[0]['reply'] = self.article('kds').body + ' Qual é a maior dificuldade hoje na sua operação?'
        answer, _ = self.answer('', self.selection(question='pain'), conv=conv)
        self.assertEqual(answer, self.article('kds').body)

    def test_business_and_channel_questions_already_answered_are_suppressed(self):
        for question in ('business', 'channels'):
            answer, _ = self.answer('minha loja vende acai e lanxe uso ifood tem cozinha?', self.selection(question=question))
            self.assertNotIn('tipo do seu estabelecimento', answer)
            self.assertNotIn('por quais canais', answer)

    def test_history_boundary_does_not_repeat_old_price(self):
        conv = conversation({'messages': 'quanto custa? | tem cozinha?'})
        conv.messages[0]['reply'] = 'Mensal: R$ 159,90 por mês, com pagamento antecipado.'
        answer, _ = self.answer('', conv=conv)
        self.assertNotIn('R$', answer)
        self.assertEqual(conversation_context(conv), 'tem cozinha?')

    def test_trace_has_revision_and_hash_without_customer_evidence(self):
        conv = conversation({'messages': 'tem cozinha?'})
        choice = self.selection()
        plan = build_plan(conv, choice, self.knowledge)
        self.assertFalse(plan.uncovered)
        for fact in plan.facts:
            self.assertIn(fact.text, self.article(fact.slug).body)
            self.assertEqual(fact.version, 3)
            self.assertEqual(len(fact.body_sha256), 64)
        trace = {}
        self.classifier.return_value = choice
        compose(conv, self.publication, self.knowledge, trace=trace)
        self.assertIn('selection', trace)
        self.assertIn('facts', trace['plan'])
        self.assertNotIn('tem cozinha?', str(trace))

    def test_demo_and_signup_only_use_approved_control_urls(self):
        control = SimpleNamespace(demo_url='https://demo.example.com/', contact_url='https://example.com/contact')
        with patch('apps.prospecting.commercial_models.CommercialControl.objects') as objects:
            objects.filter.return_value.first.return_value = control
            for message, url in (('quero demonstração', control.demo_url), ('quero contratar', control.contact_url)):
                answer, _ = self.answer(message)
                self.assertIn(url, answer)
                self.assertNotIn('Quer que eu', answer)
            control.demo_url = 'https://user:secret@example.com'
            with self.assertRaisesRegex(ValueError, 'commercial_demo_human_required'):
                self.answer('quero demonstração')

    def test_independent_integration_question_survives_channel_objection(self):
        answer, _ = self.answer('só vendo por ifood isso me ajuda? integra os pedidos?')
        self.assertIn('pedidos diretos', answer)
        self.assertIn('homologação', answer)
