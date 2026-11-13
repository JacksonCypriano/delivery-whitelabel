"""Regressões das descobertas na bateria de 20 cenários."""
import json
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase
from .commercial_quality_p14 import (
    business_overview_requested, fiscal_needs_human, soften_value_objection,
)
from .commercial_local_nlu import normalize


class CommercialQualityP14Tests(SimpleTestCase):
    def test_common_fiscal_questions_have_official_policy_p15(self):
        samples = (
            'O sistema faz emissão de nota fiscal eletrônica automaticamente?',
            'Vocês emitem NF-e?',
            'Tem emissão de NFC-e?',
            'Posso gerar cupom fiscal?',
            'Tem emissão de documento fiscal?',
            'O sistema emite documento fiscal?',
            'Vocês geram documentos fiscais?',
        )
        for question in samples:
            with self.subTest(question=question):
                self.assertFalse(fiscal_needs_human(normalize(question)))

    def test_non_fiscal_comprovante_keeps_existing_safe_route(self):
        for question in ('Tem impressão de comprovantes de cozinha?',
                         'Imprime pedidos?', 'Como funciona KDS?',
                         'Tem comprovante não fiscal na cozinha?',
                         'Documento não fiscal para impressão?'):
            self.assertFalse(fiscal_needs_human(normalize(question)))

    def test_business_overview_is_explicit(self):
        self.assertTrue(business_overview_requested(normalize('Tenho uma pizzaria, o que o sistema faz?')))
        self.assertTrue(business_overview_requested(normalize('Tenho uma hamburgueria, como o sistema funciona?')))
        # O normalizador converte 'funcionalidades' em 'funcionalidade'.
        for question in (
            'Tenho restaurante, quais as funcionalidades?',
            'Quais são as funcionalidades do sistema?',
            'Quais os recursos do VemDeDelivery?',
            'Quais são as funções da plataforma?',
        ):
            with self.subTest(question=question):
                self.assertTrue(business_overview_requested(normalize(question)))
        self.assertFalse(business_overview_requested(normalize('Tenho uma pizzaria.')))
        self.assertFalse(business_overview_requested(normalize('Quanto custa o plano anual?')))

    def test_value_objection_without_unapproved_promise(self):
        approved = 'Para avaliar o custo, considere reunir cardápio próprio, pedidos e cozinha.'
        text = soften_value_objection(approved)
        self.assertIn(approved, text)
        self.assertTrue(text.startswith('Entendo sua preocupação'))
        self.assertNotIn('garant', text.lower())
        self.assertEqual(soften_value_objection('Outro assunto'), 'Outro assunto')


class _ConversationRows:
    """Consulta read-only para exercitar o compose real sem banco nem WhatsApp."""

    def __init__(self, text):
        self.rows = [{'pk': 1, 'text': text, 'reply': '', 'from_me': False,
                      'created_at': None, 'state': 'queued'}]

    def order_by(self, *_):
        return self

    def values(self, *_):
        return self.rows


class CommercialQualityP141RegressionTests(SimpleTestCase):
    """Regressões do motor inteiro com artigos versionados da fixture oficial.

    Nenhum modelo de IA, banco de dados ou requisição externa é utilizado.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from .commercial_local import compose, HumanReview
        cls.compose_local = staticmethod(compose)
        cls.HumanReview = HumanReview
        fixture = Path(__file__).resolve().parent / 'fixtures' / 'commercial_copy_final.json'
        data = json.loads(fixture.read_text(encoding='utf-8'))
        cls.knowledge = [SimpleNamespace(pk=index, version=1, published=True, **article)
                         for index, article in enumerate(data, 1)]
        cls.publication = {'valid': True, 'data': {'plans': [
            {'name': 'Mensal', 'months': 1, 'total': '149.90', 'discount': '0'},
            {'name': 'Trimestral', 'months': 3, 'total': '427.22', 'discount': '5'},
            {'name': 'Semestral', 'months': 6, 'total': '809.46', 'discount': '10'},
            {'name': 'Anual', 'months': 12, 'total': '1528.98', 'discount': '15'},
        ]}}

    def answer(self, text, *, articles=None):
        conversation = SimpleNamespace(messages=_ConversationRows(text))
        trace = {}
        reply, ids = self.compose_local(
            conversation, self.publication, self.knowledge if articles is None else articles,
            trace=trace, handoff_signup=True,
        )
        return reply, ids, trace

    def test_three_production_failures_fixed_without_fake_features(self):
        for question in ('Tenho uma pizzaria, o que o sistema faz?',
                         'Tenho hamburgueria. Como o sistema funciona?',
                         'Tenho restaurante, quais as funcionalidades?',
                         'Quais são as funcionalidades do sistema?',
                         'Quais os recursos do VemDeDelivery?',
                         'Quais são as funções da plataforma?'):
            with self.subTest(question=question):
                reply, ids, trace = self.answer(question)
                for term in ('cardápio', 'painel operacional', 'KDS', 'conforme'):
                    self.assertIn(term, reply)
                self.assertNotIn('O VemDeDelivery atende restaurantes, pizzarias', reply)
                self.assertGreaterEqual(len(set(ids)), 1)
                self.assertIn('beneficios', trace['fulfilled'])
                self.assertTrue(all(fact['article_id'] in ids for fact in trace['facts']))

    def test_official_published_article_conditions_stay_verbatim(self):
        reply, _, _ = self.answer('Tenho uma pizzaria, o que o sistema faz?')
        self.assertIn('Resultados dependem da operação da loja.', reply)
        self.assertIn('conforme recursos habilitados', reply)
        self.assertIn('o fluxo configurado', reply)
        self.assertEqual(reply.count('Qual é a maior dificuldade hoje na sua operação?'), 1)

    def test_missing_approved_overview_source_fails_closed(self):
        without_kds = [a for a in self.knowledge if a.slug != 'visao-geral']
        with self.assertRaisesRegex(self.HumanReview, 'commercial_topics_uncovered'):
            self.answer('Tenho hamburgueria, como o sistema funciona?', articles=without_kds)

    def test_undocumented_tax_procedures_still_require_human_p15(self):
        for question in ('Qual CFOP da nota fiscal?', 'Vocês emitem NFS-e?',
                         'Quando enviam a nota fiscal da assinatura?',
                         'Nota fiscal da mensalidade automática?'):
            with self.subTest(question=question):
                with self.assertRaisesRegex(self.HumanReview, 'commercial_fiscal_review_required'):
                    self.answer(question)

    def test_print_receipt_is_not_nfe_nor_kds(self):
        for question in ('Imprime pedidos da cozinha?',
                         'Tem impressão de pedidos na cozinha?',
                         'Como funciona a impressão dos comprovantes de cozinha?'):
            with self.subTest(question=question):
                reply, _, _ = self.answer(question)
                self.assertIn('impressão de comprovantes', reply)
                self.assertNotIn('KDS é a tela', reply)
                self.assertNotIn('O painel operacional organiza', reply)

    def test_commissions_do_not_include_unrelated_order_board(self):
        for question in ('Vocês cobram comissão por pedido direto?',
                         'Tem comissão sobre pedidos?',
                         'Qual a comissão por pedidos diretos?'):
            with self.subTest(question=question):
                reply, _, _ = self.answer(question)
                self.assertIn('não cobra comissão', reply)
                self.assertNotIn('O painel operacional', reply)
                self.assertNotIn('KDS', reply)

    def test_distinct_print_kds_order_questions_are_not_lost(self):
        reply, _, _ = self.answer('Integra com iFood? Tem KDS, impressão e painel de pedidos?')
        for term in ('iFood', 'KDS', 'impressão', 'painel operacional'):
            self.assertIn(term, reply)

    def test_product_overview_and_price_retain_independent_catalog(self):
        reply, _, _ = self.answer('Tenho uma hamburgueria, como o sistema funciona e quanto custa?')
        for term in ('cardápio', 'painel operacional', 'KDS', 'R$ 149,90'):
            self.assertIn(term, reply)
        self.assertNotIn('Qual é a maior dificuldade hoje na sua operação?', reply)

    def test_business_only_does_not_force_unasked_sales_pitch(self):
        reply, _, _ = self.answer('Tenho uma pizzaria.')
        self.assertEqual(reply, 'Qual é a maior dificuldade hoje na sua operação?')

    def test_specific_billing_question_does_not_append_overview(self):
        reply, ids, _ = self.answer('Quanto custa o plano anual?')
        self.assertIn('R$ 1.528,98', reply)
        self.assertNotIn('KDS', reply)
        self.assertEqual(ids, [])
