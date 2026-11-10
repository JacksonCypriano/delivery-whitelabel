"""Pacote 13: regressões deterministicas, sem API, instancia ou WhatsApp real."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from .commercial_greetings import enhance_reply, presentation_for
from .commercial_local_nlu import intents_for

TZ = ZoneInfo('America/Sao_Paulo')


class FakeMessages:
    def __init__(self, rows):
        self.rows = rows

    def exclude(self, **kwargs):
        return FakeMessages([r for r in self.rows if r['pk'] != kwargs['pk']])

    def order_by(self, *_):
        return FakeMessages(sorted(self.rows, key=lambda r: r['pk'], reverse=True))

    def values(self, *_):
        return [dict(row) for row in self.rows]


class GreetingTests(SimpleTestCase):
    def make(self, stamp, prior=(), text='Quanto custa?'):
        message = SimpleNamespace(pk=100, created_at=stamp, text=text)
        conversation = SimpleNamespace(messages=FakeMessages(list(prior)))
        return conversation, message

    def row(self, pk, stamp, state='submitted', reply='Mensal: R$ 149,90', from_me=False):
        return {'pk': pk, 'created_at': stamp, 'reply': reply,
                'state': state, 'from_me': from_me, 'text': 'Quanto custa?'}

    @override_settings(TIME_ZONE='America/Sao_Paulo')
    def test_first_real_reply_greets_even_with_held_legacy_message(self):
        stamp = datetime(2026, 11, 10, 14, 0, tzinfo=TZ)
        conv, message = self.make(stamp, [self.row(1, stamp-timedelta(days=4), state='held', reply='')])
        reply = enhance_reply(conv, message, 'Mensal: R$ 149,90 por mês, com pagamento antecipado.')
        self.assertIn('Boa tarde!', reply)
        self.assertIn('assistente virtual comercial do VemDeDelivery', reply)
        self.assertIn('R$ 149,90', reply)
        self.assertEqual(reply.count('Qual é o tipo do seu estabelecimento?'), 1)

    @override_settings(TIME_ZONE='America/Sao_Paulo')
    def test_recent_followup_does_not_repeat_greeting(self):
        stamp = datetime(2026, 11, 10, 15, 0, tzinfo=TZ)
        conv, message = self.make(stamp, [self.row(1, stamp-timedelta(minutes=10))])
        self.assertEqual(enhance_reply(conv, message, 'Temos integração com iFood.'), 'Temos integração com iFood.')

    @override_settings(TIME_ZONE='America/Sao_Paulo')
    def test_midnight_30_minutes_no_greeting(self):
        stamp = datetime(2026, 11, 11, 0, 20, tzinfo=TZ)
        conv, message = self.make(stamp, [self.row(1, stamp-timedelta(minutes=30))])
        self.assertEqual(presentation_for(conv, message), '')

    @override_settings(TIME_ZONE='America/Sao_Paulo')
    def test_next_day_after_six_hours_brief_greeting(self):
        stamp = datetime(2026, 11, 11, 7, 0, tzinfo=TZ)
        conv, message = self.make(stamp, [self.row(1, datetime(2026, 11, 10, 22, 0, tzinfo=TZ))])
        result = presentation_for(conv, message)
        self.assertIn('Bom dia!', result)
        self.assertNotIn('Sou o assistente', result)

    @override_settings(TIME_ZONE='America/Sao_Paulo')
    def test_same_day_eight_hours_brief_greeting(self):
        stamp = datetime(2026, 11, 10, 21, 0, tzinfo=TZ)
        conv, message = self.make(stamp, [self.row(1, datetime(2026, 11, 10, 12, 0, tzinfo=TZ))])
        self.assertIn('Boa noite!', presentation_for(conv, message))

    @override_settings(TIME_ZONE='America/Sao_Paulo')
    def test_uncertain_and_held_do_not_prove_delivery(self):
        stamp = datetime(2026, 11, 10, 15, 0, tzinfo=TZ)
        prior = [self.row(1, stamp-timedelta(minutes=1), state='uncertain'),
                 self.row(2, stamp-timedelta(minutes=2), state='held')]
        conv, message = self.make(stamp, prior)
        self.assertIn('Sou o assistente virtual', presentation_for(conv, message))

    @override_settings(TIME_ZONE='America/Sao_Paulo')
    def test_human_sent_message_prevents_full_reintroduction(self):
        stamp = datetime(2026, 11, 11, 11, 0, tzinfo=TZ)
        conv, message = self.make(stamp, [self.row(1, stamp-timedelta(days=1), from_me=True, reply='')])
        self.assertNotIn('assistente virtual', presentation_for(conv, message))

    def test_explicit_kds_and_order_panel_remain_two_intents(self):
        topics, _ = intents_for('O sistema organiza os pedidos do iFood e tem tela para a cozinha e impressao?')
        self.assertTrue({'pedidos', 'cozinha', 'integracoes', 'impressao'} <= topics)

    def test_whatsapp_as_order_source_is_not_feature_request(self):
        topics, _ = intents_for('Tenho uma pizzaria e recebo pedidos pelo iFood e WhatsApp. Tem tela da cozinha e impressao?')
        self.assertNotIn('whatsapp', topics)
        self.assertIn('cozinha', topics)

    def test_direct_agent_question_still_recognized(self):
        topics, _ = intents_for('O agente de atendimento automatico responde no whatsapp?')
        self.assertIn('whatsapp', topics)
