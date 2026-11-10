"""Regressões das descobertas na bateria de 20 cenários."""
from django.test import SimpleTestCase
from .commercial_quality_p14 import (
    business_overview_requested, fiscal_needs_human, soften_value_objection,
)
from .commercial_local_nlu import normalize


class CommercialQualityP14Tests(SimpleTestCase):
    def test_fiscal_questions_require_review(self):
        samples = (
            'O sistema faz emissão de nota fiscal eletrônica automaticamente?',
            'Vocês emitem NF-e?',
            'Tem emissão de NFC-e?',
            'Posso gerar cupom fiscal?',
        )
        for question in samples:
            with self.subTest(question=question):
                self.assertTrue(fiscal_needs_human(normalize(question)))

    def test_non_fiscal_comprovante_keeps_existing_safe_route(self):
        for question in ('Tem impressão de comprovantes de cozinha?',
                         'Imprime pedidos?', 'Como funciona KDS?'):
            self.assertFalse(fiscal_needs_human(normalize(question)))

    def test_business_overview_is_explicit(self):
        self.assertTrue(business_overview_requested(normalize('Tenho uma pizzaria, o que o sistema faz?')))
        self.assertTrue(business_overview_requested(normalize('Tenho uma hamburgueria, como o sistema funciona?')))
        self.assertFalse(business_overview_requested(normalize('Tenho uma pizzaria.')))
        self.assertFalse(business_overview_requested(normalize('Quanto custa o plano anual?')))

    def test_value_objection_without_unapproved_promise(self):
        approved = 'Para avaliar o custo, considere reunir cardápio próprio, pedidos e cozinha.'
        text = soften_value_objection(approved)
        self.assertIn(approved, text)
        self.assertTrue(text.startswith('Entendo sua preocupação'))
        self.assertNotIn('garant', text.lower())
        self.assertEqual(soften_value_objection('Outro assunto'), 'Outro assunto')
