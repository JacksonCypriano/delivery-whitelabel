"""Final-quality regressions, authored but not executed during package delivery."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from .commercial_local import compose, HumanReview
from .commercial_local_battery import CASES, conversation, evaluate
from .commercial_copy import PREFIX, units


class FinalCopyTests(TestCase):
    def setUp(self):
        rows = json.loads((Path(__file__).parent / 'fixtures' / 'commercial_copy_final.json').read_text())
        self.knowledge = [SimpleNamespace(**row, pk=i, version=2, published=True) for i, row in enumerate(rows, 1)]
        self.publication = dict(valid=True, fingerprint='test', data=dict(payments=['pix'], plans=[
            dict(name='Mensal', months=1, total='159.90', discount=0),
            dict(name='Anual', months=12, total='1630.98', discount=15)]))
        self.links = dict(demo='https://demo.example.com/', signup='https://example.com/contact')
        self.net = patch('requests.sessions.Session.request', side_effect=AssertionError('No network')).start()
        self.addCleanup(patch.stopall)

    def answer(self, text, conv=None, trace=None):
        return compose(conv or conversation(dict(messages=text)), self.publication,
                       self.knowledge, links=self.links, trace=trace)[0]

    def test_reviewed_units_have_valid_shape_and_fit_publication_limit(self):
        for article in self.knowledge:
            with self.subTest(slug=article.slug):
                self.assertLessEqual(len(article.body), 1100)
                self.assertTrue(units(article))
                self.assertNotIn('R$', article.body)
                self.assertNotIn('https://', article.body)

    def test_cardapio_whatsapp_pix_without_commission_detour(self):
        answer = self.answer('tem cardapio online whatsapp e pix?')
        for word in ('cardápio', 'WhatsApp', 'Pix', 'aprovação', 'subconta'):
            self.assertIn(word, answer)
        self.assertNotIn('comissão', answer)
        self.assertLessEqual(len(answer), 500)

    def test_centralization_and_kitchen_are_distinct(self):
        answer = self.answer('posso usar ifood e pedidos do site na mesma tela?')
        self.assertIn('central operacional', answer)
        self.assertIn('homologação', answer)
        self.assertNotIn('99Food', answer)
        self.assertLessEqual(len(answer), 500)
        answer = self.answer('tem kanban da cozinha com pedidos novos e prontos?')
        self.assertIn('painel operacional', answer)
        self.assertIn('KDS', answer)
        self.assertIn('etapas', answer)
        self.assertNotIn('impressão', answer)

    def test_differentials_without_promised_revenue(self):
        answer = self.answer('qual a diferença de um app de delivery?')
        for word in ('cardápio', 'diretas', 'WhatsApp', 'cozinha', 'comissão', 'independentes'):
            self.assertIn(word, answer)
        self.assertNotIn('aumento garantido', answer)
        self.assertLessEqual(len(answer), 500)

    def test_crm_automation_coverage_requires_consent_and_publication(self):
        answer = self.answer('quero cardapio pedidos CRM e automacao')
        for word in ('cardápio', 'pedidos', 'CRM', 'automações', 'consentimento'):
            self.assertIn(word, answer)
        self.assertNotIn('grátis', answer)
        # A draft must never provide the missing features.
        next(a for a in self.knowledge if a.slug == 'gestao').published = False
        with self.assertRaises(HumanReview):
            self.answer('quero cardapio pedidos CRM e automacao')

    def test_table_and_courier_print_data_not_invented(self):
        for text in ('tem pedido de mesa retirada e entrega?', 'imprime dados do motoboy e endereço?'):
            with self.subTest(text=text), self.assertRaises(HumanReview):
                self.answer(text)
        answer = self.answer('imprime endereço e itens?')
        self.assertIn('endereço', answer)
        self.assertIn('não fiscal', answer)
        self.assertIn('compatibilidade', answer)

    def test_critical_service_and_broadcast_guards_preserved(self):
        cases = {r['id']: r for r in json.loads(CASES.read_text())}
        for case_id in ('19', '57', '71'):
            row = evaluate(cases[case_id], self.publication, self.knowledge, self.links)
            self.assertEqual(row['outcome'], 'human')
            self.assertEqual(row['answer'], '')
        self.net.assert_not_called()

    def test_negation_and_period_coreference(self):
        self.assertNotIn('Acesse', self.answer('não quero demonstração'))
        self.assertIn('KDS', self.answer('não quero demonstração, tem cozinha?'))
        conv = conversation(dict(messages='quanto custa o anual? | quanto fica esse plano?'))
        conv.messages[0]['reply'] = 'Anual: R$ 1.630,98 por 12 meses, com 15% de desconto e pagamento antecipado.'
        answer = self.answer('', conv)
        self.assertIn('1.630,98', answer)
        self.assertNotIn('159,90', answer)
        self.assertNotIn('Acesse', self.answer('não quero contratar'))

    def test_human_and_held_states_reset_memory(self):
        for state in ('human', 'held', 'uncertain'):
            conv = conversation(dict(messages='quero demonstração | isso?'))
            conv.messages[0]['state'] = state
            answer = self.answer('', conv)
            self.assertNotIn(self.links['demo'], answer)

    def test_oversized_pending_window_is_not_silently_truncated(self):
        with self.assertRaisesRegex(ValueError, 'context_requires_human'):
            self.answer(' | '.join(['tem cozinha?'] * 7))

    def test_quality_dimensions_are_separate_and_never_editorially_approved(self):
        row = evaluate(dict(id='quality', messages='tem cozinha?', expectation='answer'),
                       self.publication, self.knowledge, self.links)
        self.assertTrue(row['outcome_compatible'])
        self.assertEqual(row['quality']['factual_completeness']['missing'], [])
        self.assertTrue(row['quality']['commercial_safety']['facts_match_published_revision'])
        self.assertEqual(row['quality']['editorial_quality'], 'pending')
        self.assertTrue(row['quality']['manual_review_required'])

    def test_unapproved_price_or_link_inside_unit_is_rejected(self):
        article = self.knowledge[0]
        article.body = PREFIX + json.dumps([{'for': ['cardapio'], 'text': 'Grátis por R$ 0,00 em https://bad.example'}])
        with self.assertRaises(ValueError):
            units(article)
