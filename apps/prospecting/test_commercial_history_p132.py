"""Regressão 13.2: memória factual consultável sem respostas inventadas."""
from datetime import timedelta
from unittest.mock import MagicMock

from django.test import SimpleTestCase
from django.utils import timezone

from .commercial_history import answer_history_question, historical_facts, requested_history_topics


class _Conversation:
    def __init__(self, rows):
        self.messages = MagicMock()
        self.rows = rows
        self.messages.filter.return_value.order_by.return_value.values.return_value.__getitem__.side_effect = lambda sl: self.rows[sl]


class CommercialHistoryTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()

    def row(self, text):
        return {'text': text, 'created_at': self.now - timedelta(minutes=10)}

    def test_remembers_business_and_annual_plan_from_previous_messages(self):
        conv = _Conversation([
            self.row('Minha pizzaria recebe pedidos pelo iFood e WhatsApp. O plano anual custa quanto?'),
            self.row('Tenho uma pizzaria e quero conhecer o sistema.'),
        ])
        result, topics = answer_history_question(
            conv,
            'Você lembra qual é o meu tipo de estabelecimento? E qual foi o plano que eu perguntei anteriormente?',
            now=self.now,
        )
        self.assertEqual(topics, {'business', 'period'})
        self.assertIn('pizzaria', result)
        self.assertIn('anual', result)
        self.assertNotIn('mensal', result)

    def test_does_not_guess_missing_information(self):
        conv = _Conversation([self.row('Quero conhecer o sistema')])
        result, _ = answer_history_question(conv, 'Você lembra do meu ramo e qual plano perguntei antes?', now=self.now)
        self.assertIn('Não encontrei', result)
        self.assertNotIn('pizzaria', result)
        self.assertNotIn('R$', result)

    def test_regular_pricing_question_not_intercepted(self):
        self.assertIsNone(answer_history_question(_Conversation([]), 'Quanto custa o plano mensal?', now=self.now))
        self.assertEqual(requested_history_topics('Qual o valor do plano anual?'), set())

    def test_only_prior_processed_messages_are_requested(self):
        conv = _Conversation([])
        historical_facts(conv, now=self.now)
        filters = conv.messages.filter.call_args.kwargs
        self.assertEqual(filters['from_me'], False)
        self.assertNotIn('held', filters['state__in'])
        self.assertNotIn('uncertain', filters['state__in'])
        self.assertNotIn('human', filters['state__in'])

    def test_latest_explicit_period_takes_precedence(self):
        conv = _Conversation([self.row('E qual o valor do plano anual?'), self.row('Quanto custa o plano mensal?')])
        facts = historical_facts(conv, now=self.now)
        self.assertEqual(facts['period'], 'anual')
