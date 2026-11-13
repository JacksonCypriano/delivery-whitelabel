"""P15 regressions: authored for CI, never run during package preparation."""
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from .commercial_local import compose, HumanReview
from .commercial_local_battery import conversation
from .commercial_local_nlu import normalize, intents_for
from .commercial_quality_p14 import fiscal_scope


class CommercialPackage15Tests(SimpleTestCase):
    def setUp(self):
        rows = json.loads((Path(__file__).parent / 'fixtures/commercial_copy_final.json').read_text())
        self.knowledge = [SimpleNamespace(**row, pk=i, version=1, published=True)
                          for i, row in enumerate(rows, 1)]
        self.publication = {'fingerprint': 'fixture', 'data': {'plans': [
            {'name': 'Mensal', 'months': 1, 'total': '149.90', 'discount': 0},
            {'name': 'Anual', 'months': 12, 'total': '1528.98', 'discount': 15},
        ], 'payments': ['pix', 'card']}}
        self.net = patch('requests.sessions.Session.request', side_effect=AssertionError('No network')).start()
        self.addCleanup(patch.stopall)

    def answer(self, text, *, prior=None, prior_state='submitted', trace=None):
        conv = conversation({'messages': (prior + ' | ' if prior else '') + text})
        if prior:
            conv.messages[0].update(reply='Resposta anterior.', state=prior_state)
        return compose(conv, self.publication, self.knowledge,
                       links={'demo': 'https://demo.example.com/'},
                       handoff_signup=True, trace=trace)[0]

    def test_service_invoice_variants_without_price_or_store_pitch(self):
        for text in ('Preciso da nota fiscal da mensalidade.',
                     'Consigo nota fiscal da assinatura anual?',
                     'Recebo nota fiscal da contratação?', 'Recebo nota fiscal quando contrato?',
                     'NF para a empresa contratante?',
                     'Minha empresa precisa de nota fiscal do serviço.',
                     'Vocês faturam para CNPJ?', 'Tem NF do valor que pago?',
                     'Vcs manda nota do pagamento?', 'Tem nota fiscal da plataforma?',
                     'vcs emite notafisca da mensalidade'):
            with self.subTest(text=text):
                answer = self.answer(text)
                self.assertIn('emite nota fiscal', answer)
                for forbidden in ('não possui integração', 'R$', 'automaticamente', 'KDS'):
                    self.assertNotIn(forbidden, answer)

    def test_store_invoice_variants_never_promise_emission(self):
        for text in ('O sistema emite nota fiscal para meus clientes?',
                     'Quando vendo uma pizza ele gera nota?',
                     'Tem emissão de NFC-e?', 'Emite NF-e automaticamente nos pedidos?',
                     'Integra com algum emissor fiscal?', 'Tem emissão fiscal no caixa?',
                     'O pedido já sai com nota fiscal?',
                     'Consigo emitir nota das venda?', 'Consigo automatizar as notas da minha hamburgueria?', 'Nota fiscal da minha hamburgueria?'):
            with self.subTest(text=text):
                answer = self.answer(text)
                self.assertIn('não possui integração', answer)
                self.assertIn('não substituem uma nota fiscal', answer)
                self.assertNotIn('Sim!', answer)
                self.assertNotIn('O painel operacional', answer)

    def test_ambiguous_question_and_disambiguation(self):
        answer = self.answer('Vocês emitem nota fiscal?')
        for text in ('serviços contratados', 'não possui integração', 'Você está perguntando'):
            self.assertIn(text, answer)
        self.assertIn('assinatura', self.answer('Da assinatura', prior='Vocês emitem nota fiscal?'))
        self.assertNotIn('Sim!', self.answer('E das vendas?', prior='Preciso da nota fiscal da mensalidade.'))

    def test_context_resolves_only_this_conversation(self):
        self.assertNotIn('não possui integração', self.answer('E a nota fiscal?', prior='Quanto custa o plano anual?'))
        self.assertIn('não possui integração', self.answer('E a nota fiscal?', prior='Recebo pedidos da minha loja.'))
        self.assertNotIn('Sim!', self.answer('Vocês emitem?', prior='Nota fiscal dos pedidos?'))
        self.assertIn('Você está perguntando', self.answer('E a nota fiscal?'))
        self.assertIn('Você está perguntando', self.answer('E a nota fiscal?', prior='Quanto custa o anual?', prior_state='held'))

    def test_human_boundary_and_expired_memory(self):
        for state in ('human', 'uncertain', 'sending'):
            with self.subTest(state=state):
                self.assertIn('Você está perguntando', self.answer('Nota fiscal?', prior='Plano anual', prior_state=state))
        conv = conversation({'messages': 'Plano anual | Nota fiscal?'})
        conv.messages[0].update(reply='Anterior', state='submitted')
        conv.messages[0]['created_at'] -= timedelta(hours=1)
        answer, _ = compose(conv, self.publication, self.knowledge)
        self.assertIn('Você está perguntando', answer)

    def test_mixed_questions_preserve_every_known_answer(self):
        trace = {}
        answer = self.answer('Quanto custa, integra com iFood, tem KDS e emite nota?', trace=trace)
        for term in ('149,90', 'iFood', 'homologação', 'KDS', 'não possui integração'):
            self.assertIn(term, answer)
        self.assertEqual(set(trace['fulfilled']), {'pricing', 'integracoes', 'cozinha', 'fiscal'})
        self.assertTrue(trace['facts'])

    def test_real_tax_procedures_and_signup_still_handoff(self):
        for text in ('Qual CFOP da nota fiscal?', 'Qual alíquota de ISS na nota fiscal?',
                     'Quando emitem nota fiscal da assinatura?', 'Envia XML da nota fiscal?',
                     'Tem certificado A1 para emitir NF-e?', 'Vocês emitem NFS-e?',
                     'Nota fiscal da mensalidade automática?',
                     'Quanto custa e qual CFOP da nota fiscal?',
                     'Quero contratar, mas preciso de nota fiscal.',
                     'blz como contrato', 'quero fecha', 'quero falar com uma pessoa'):
            with self.subTest(text=text), self.assertRaises(HumanReview):
                self.answer(text)
        self.net.assert_not_called()

    def test_missing_draft_or_legacy_fiscal_article_fails_closed(self):
        article = next(a for a in self.knowledge if a.slug == 'notas-fiscais')
        article.published = False
        with self.assertRaises(HumanReview):
            self.answer('Nota fiscal da mensalidade?')
        article.published = True
        draft = deepcopy(article)
        draft.pk, draft.version, draft.published = 999, 2, False
        self.knowledge.append(draft)
        with self.assertRaises(HumanReview):
            self.answer('Nota fiscal dos pedidos?')
        self.knowledge.pop()
        article.body = 'Emitimos qualquer documento automaticamente.'
        with self.assertRaises(HumanReview):
            self.answer('Nota fiscal da mensalidade?')

    def test_non_fiscal_receipt_not_classified_as_tax_request(self):
        for text in ('Tem comprovante não fiscal na cozinha?', 'imprime comanda', 'tem impreçora'):
            with self.subTest(text=text):
                self.assertIsNone(fiscal_scope(normalize(text)))
                answer = self.answer(text)
                self.assertIn('compatibilidade', answer)
                self.assertNotIn('Sim!', answer)

    def test_overview_has_one_mention_of_each_core_benefit(self):
        for business in ('pizzaria', 'hamburgueria', 'restaurante', 'lanchonete'):
            answer = self.answer(f'Tenho uma {business}, como o sistema funciona?')
            for term in ('cardápio', 'painel operacional', 'KDS', 'WhatsApp'):
                self.assertEqual(answer.count(term), 1)
            self.assertIn('conforme recursos habilitados', answer)
            self.assertIn('Resultados dependem', answer)
            self.assertLess(len(answer), 550)
        self.assertIn('KDS', self.answer('como funsiona'))
        self.assertNotIn('Qual é a maior dificuldade', self.answer(
            'Como o sistema funciona?', prior='Minha dificuldade é organizar pedidos.'))

    def test_catalog_monthly_equivalent_is_dynamic_and_prepaid(self):
        answer = self.answer('Quanto sai por mês no plano anual?')
        for term in ('1.528,98', '127,42', 'antecipado', 'não uma cobrança mensal'):
            self.assertIn(term, answer)
        self.assertNotIn('Mensal:', answer)
        self.publication['data']['plans'][1]['total'] = '1800.00'
        self.assertIn('150,00', self.answer('Quanto sai por mês no anual?'))

    def test_specific_questions_and_negated_actions(self):
        self.assertNotIn('KDS', self.answer('qto custa'))
        self.assertNotIn('R$', self.answer('tem cardapioo'))
        self.assertIn('demonstração', self.answer('quero demonstração'))
        self.assertNotIn('Acesse', self.answer('não quero demonstração'))
        self.assertNotIn('signup', intents_for('não quero fechar')[0])
        self.assertNotIn('signup', intents_for('não quero contratar')[0])
