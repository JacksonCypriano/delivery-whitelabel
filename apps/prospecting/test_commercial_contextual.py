"""Local regression suite; written, NOT executed during delivery.

The original battery remains immutable. Fixtures represent approved copy for
unit testing only; operational replies always read published Django revisions.
"""
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from django.test import override_settings

from .commercial_local import compose, HumanReview
from .commercial_local_battery import CASES, conversation, evaluate, snapshot, read_snapshot
from .commercial_local_nlu import normalize
from .management.commands.prepare_commercial_knowledge import ARTICLES
from .management.commands.prepare_commercial_package07 import ARTICLES as OBJECTIONS
from .management.commands.prepare_commercial_package08 import ARTICLES as SHORT
from .test_commercial_package09 import BODIES


# Reviewed semantic obligations grouped by capability, not canned answers.
# These supplement, never replace, the original outcome expectations.
OBLIGATIONS = (
    ('pricing', (1, 2, 3, 4, 5, 6, 7, 11, 14, 17, 22, 27, 32, 38, 61, 62, 64, 65, 70), ('R$', 'antecipado')),
    ('comissoes', (3, 17, 29), ('comissão', 'independentes')),
    ('cardapio', (21, 30, 31), ('cardápio',)),
    ('cozinha', (11, 14, 34, 63, 70), ('KDS',)),
    ('impressao', (11, 13, 23, 40, 50, 65), ('impressão', 'compatibilidade')),
    ('integracoes', (13, 25, 30, 37, 41, 43, 63), ('iFood', 'homologação')),
    ('modalidades', (14, 24, 66), ('entrega', 'retirada')),
    ('whatsapp', (26, 33, 35, 51, 53, 59, 64), ('WhatsApp',)),
    ('beneficios', (17, 28, 39), ('plataforma',)),
    ('gestao', (59, 67), ('adicionais',)),
    ('pedidos', (46,), ('painel', 'etapas')),
    ('objecao-valor', (91,), ('não há garantia',)),
    ('objecao-canais', (92, 93), ('pedidos diretos', 'liberação')),
    ('demo', (94,), ('https://demo.example.com/',)),
)


class ContextualCommercialTests(TestCase):
    def setUp(self):
        bodies = {s: b for s, _, b in (*ARTICLES, *OBJECTIONS, *SHORT)}
        bodies.update(BODIES)
        bodies['gestao'] = ('A loja pode configurar identidade visual, produtos, categorias, fotos, preços, descrições, adicionais e personalizações, incluindo opções de pizzas meio a meio. '
                             'Também pode configurar horários, bairros, taxas de entrega e retirada. '
                             'A plataforma oferece recursos de clientes, histórico, cupons, promoções e disponibilidade de produtos. '
                             'Funcionalidades específicas dependem das permissões e configurações do estabelecimento.')
        self.knowledge = [SimpleNamespace(pk=i, slug=s, title=s, body=b, version=1, published=True)
                          for i, (s, b) in enumerate(bodies.items(), 1)]
        self.publication = dict(valid=True, fingerprint='unit-test', data=dict(payments=['pix', 'boleto'], plans=[
            dict(name='Mensal', months=1, total='159.90', discount=0),
            dict(name='Trimestral', months=3, total='455.72', discount=5),
            dict(name='Semestral', months=6, total='863.46', discount=10),
            dict(name='Anual', months=12, total='1630.98', discount=15)]))
        self.links = dict(demo='https://demo.example.com/', signup='https://example.com/contato')
        # An accidental provider call fails the test rather than making a request.
        self.network = patch('requests.sessions.Session.request', side_effect=AssertionError('network forbidden')).start()
        self.addCleanup(patch.stopall)

    def answer(self, text, **kwargs):
        return compose(conversation({'messages': text}), self.publication, self.knowledge,
                       links=self.links, **kwargs)[0]

    def test_original_100_cases_outcomes_and_no_external_requests(self):
        cases = json.loads(CASES.read_text())
        self.assertEqual(len(cases), 100)
        self.assertEqual(len({case['id'] for case in cases}), 100)
        self.assertEqual(hashlib.sha256(CASES.read_bytes()).hexdigest(),
                         'da415be90d8e684b570271b13d9a90ab7ce92c45044380f90ee9dd989ada6ebb')
        for case in cases:
            with self.subTest(case=case['id']):
                row = evaluate(case, self.publication, self.knowledge, self.links)
                self.assertTrue(row['outcome_compatible'], row)
                self.assertNotEqual(row['outcome'], 'execution_error')
                if row['outcome'] == 'answer':
                    self.assertTrue(row['answer'])
                    self.assertNotIn('garantimos', row['answer'].lower())
                    self.assertEqual(row['manual_quality'], 'pending')
                    for intent, ids, facts in OBLIGATIONS:
                        if int(case['id']) in ids:
                            self.assertIn(intent, row['trace']['intents'])
                            for fact in facts:
                                self.assertIn(fact, row['answer'])
        self.network.assert_not_called()

    def test_all_operational_modes_bypass_gemini_ollama_and_quota(self):
        from .commercial import compose as operational
        with patch('apps.prospecting.commercial._gemini_choice', side_effect=AssertionError), \
             patch('apps.prospecting.commercial._compose_ollama', side_effect=AssertionError), \
             patch('apps.prospecting.commercial_smart.classify', side_effect=AssertionError), \
             patch('apps.prospecting.commercial_quota.reserve', side_effect=AssertionError):
            for mode in ('smart', 'hybrid', 'ollama', 'rules', 'contextual'):
                with self.subTest(mode=mode), override_settings(COMMERCIAL_AGENT_MODE=mode):
                    answer, _ = operational(conversation({'messages': 'quanto custa?'}), self.publication, self.knowledge)
                    self.assertIn('159,90', answer)

    def test_multiple_questions_all_essential_facts_and_conditions(self):
        answer = self.answer('quanto custa tem zap cozinha imprime e integra ifood?')
        for fact in ('159,90', 'antecipado', 'WhatsApp', 'KDS', 'impressão', 'compatibilidade', 'iFood', 'homologação'):
            self.assertIn(fact, answer)
        self.assertNotIn('tipo do seu estabelecimento', answer)

    def test_spelling_plural_synonyms_and_joined_words(self):
        for question, fact in (('temcardapio', 'cardápio'), ('quantocusta', '159,90'),
                               ('vcs tem cardapiu', 'cardápio'), ('coizinha e impresora', 'impressão'),
                               ('tem adicionais', 'adicionais'), ('tem comprovante', 'impressão')):
            with self.subTest(question=question):
                self.assertIn(fact, self.answer(question))
        self.assertEqual(normalize('cartapiografia'), 'cartapiografia')

    def test_customer_information_survives_answered_turn_with_ttl(self):
        conv = conversation({'messages': 'só vendo pelo ifood | e para mim vale a pena?'})
        conv.messages[0]['reply'] = 'Qual é a maior dificuldade hoje na sua operação?'
        answer, _ = compose(conv, self.publication, self.knowledge, links=self.links)
        self.assertIn('pedidos diretos', answer)
        self.assertIn('liberação', answer)
        self.assertNotIn('maior dificuldade', answer)
        conv.messages[0]['created_at'] -= timedelta(hours=2)
        answer, _ = compose(conv, self.publication, self.knowledge, links=self.links)
        self.assertNotIn('iFood', answer)

    def test_subject_reset_and_separate_contacts_do_not_leak_context(self):
        answer = self.answer('só vendo por ifood | mudando de assunto, quanto custa?')
        self.assertIn('159,90', answer)
        self.assertNotIn('iFood', answer)
        other = self.answer('vale a pena?')
        self.assertNotIn('iFood', other)

    def test_partial_known_question_requests_clarification(self):
        trace = {}
        answer = self.answer('tem cozinha e teletransporte?', trace=trace)
        self.assertTrue(trace['clarification'])
        self.assertIn('esclarecer', answer)
        self.assertNotIn('KDS', answer)

    def test_ambiguous_cupom_and_taxa_not_guessed(self):
        self.assertIn('cupom de desconto ou impressão', self.answer('tem cupom?'))
        self.assertIn('mensalidade', self.answer('qual taxa?'))

    def test_missing_and_draft_knowledge_do_not_claim_capability(self):
        self.knowledge = [a for a in self.knowledge if a.slug != 'impressao']
        with self.assertRaises(HumanReview):
            self.answer('tem cozinha e imprime?')
        original = next(a for a in self.knowledge if a.slug == 'kds')
        draft = SimpleNamespace(**{**vars(original), 'pk': 1000, 'version': 2, 'published': False})
        self.knowledge.append(draft)
        # KDS may use the still-published operational article, never the draft.
        trace = {}
        self.answer('o que é kds?', trace=trace)
        self.assertNotIn(1000, [f['article_id'] for f in trace['facts']])

    def test_missing_specific_detail_is_not_covered_by_generic_article(self):
        with self.assertRaises(HumanReview):
            self.answer('tem estoque?')
        self.assertIn('meio a meio', self.answer('da para montar pizza meio a meio?'))

    def test_commercial_safety_before_any_composition(self):
        for text in ('garante mais vendas?', 'me dá desconto extra', 'qual impressora homologada?',
                     'transcreve áudio?', '99food liberado para todo mundo?',
                     'fornecem motoboy?', 'quero falar com uma pessoa'):
            with self.subTest(text=text), self.assertRaises(HumanReview):
                self.answer(text)
        self.assertIn('assumir', self.answer('o atendente humano consegue assumir a conversa?'))

    def test_payment_scope_and_official_links(self):
        answer = self.answer('como pagar a mensalidade? aceita pix?')
        self.assertIn('assinatura', answer)
        self.assertIn('Pix', answer)
        self.assertNotIn('cartão', answer)
        self.assertIn(self.links['demo'], self.answer('quero conhecer'))
        self.assertIn(self.links['signup'], self.answer('como faço para contratar?'))
        self.links['demo'] = 'http://example.com'
        with self.assertRaises(HumanReview):
            self.answer('quero demonstração')

    def test_price_changes_follow_catalog_not_customer_numbers(self):
        answer = self.answer('quanto custa o anual?')
        self.assertIn('1.630,98', answer)
        self.assertNotIn('149,90', answer)
        objection = self.answer('149,90 é caro, compensa?')
        self.assertNotIn('R$', objection)

    def test_snapshot_replay_and_integrity(self):
        data = snapshot(self.publication, self.knowledge, self.links)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'snapshot.json'
            path.write_text(json.dumps(data))
            publication, knowledge, links = read_snapshot(path)
            question = conversation({'messages': 'quanto custa e tem cozinha?'})
            self.assertEqual(compose(question, publication, knowledge, links=links),
                             compose(question, self.publication, self.knowledge, links=self.links))
            data['data']['articles'][0]['body'] = 'Alteração não aprovada.'
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                read_snapshot(path)

    def test_snapshot_command_needs_neither_database_nor_network(self):
        from io import StringIO
        from django.core.management import call_command
        from django.db import connection
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'snapshot.json'
            path.write_text(json.dumps(snapshot(self.publication, self.knowledge, self.links)))
            with patch.object(connection, 'cursor', side_effect=AssertionError('database forbidden')):
                call_command('run_commercial_battery_local', snapshot=path,
                             output=str(Path(tmp) / 'report'), stdout=StringIO())
            result = json.loads((Path(tmp) / 'report' / 'checkpoint.json').read_text())
            self.assertEqual(len(result['rows']), 100)
            self.assertTrue(all(row['manual_quality'] == 'pending' for row in result['rows']))
        self.network.assert_not_called()

    def test_long_approved_conditions_are_not_cut_or_sent_to_human_for_length(self):
        article = next(a for a in self.knowledge if a.slug == 'impressao')
        article.body = ('Há impressão de pedidos. A compatibilidade depende de ' +
                        'configuração e conferência ' * 35 + 'do equipamento.')
        answer = self.answer('tem impressão?')
        self.assertTrue(answer.endswith('do equipamento.'))
        self.assertGreater(len(answer), 500)

    def test_explicit_repeat_answer_is_allowed_without_repeated_pitch(self):
        conv = conversation({'messages': 'tem cozinha? | tem cozinha?'})
        conv.messages[0]['reply'] = 'KDS é a tela da cozinha para acompanhar os pedidos e suas etapas de preparo.'
        answer, _ = compose(conv, self.publication, self.knowledge, links=self.links)
        self.assertIn('KDS', answer)
        self.assertNotIn('demonstração', answer)
        self.assertEqual(answer.count('KDS'), 1)
