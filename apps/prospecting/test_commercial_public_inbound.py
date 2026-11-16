"""Regressões do opt-in ao atendimento comercial público de entrada, sem provedores reais."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from .commercial import process_message, receive
from .commercial_api import CommercialPanel
from .commercial_models import (
    CommercialControl,
    CommercialConversation,
    CommercialMessage,
    CommercialOtpExclusion,
    CommercialPilotContact,
)
from .commercial_pilot import eligible


@override_settings(
    COMMERCIAL_AGENT_ENABLED=True,
    COMMERCIAL_OTP_SHARED_ENABLED=True,
    EVOLUTION_INSTANCE='otp-legado',
    OTP_EVOLUTION_INSTANCE='comercial-publico-teste',
    PROSPECTING_EVOLUTION_INSTANCE='prospeccao-teste',
    MARKETING_WHATSAPP='5511900000000',
)
class PublicCommercialInboundTests(TestCase):
    def setUp(self):
        self.instance = 'comercial-publico-teste'
        self.phone = '5511999991234'
        self.control = CommercialControl.objects.create(
            pk=1, instance=self.instance, enabled=True,
        )

    def inbound(self, provider_id, text='Oi, quanto custa?', *, from_me=False):
        return receive(self.instance, {
            'phone': self.phone, 'message_id': provider_id,
            'text': text, 'kind': 'text', 'from_me': from_me,
        })

    @override_settings(COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=False)
    def test_padrao_continua_bloqueando_contatos_fora_do_piloto(self):
        self.assertFalse(eligible(self.phone, self.instance))
        row = self.inbound('sem-piloto')
        self.assertEqual(row.state, 'held')
        CommercialPilotContact.objects.create(phone=self.phone, active=True)
        self.assertTrue(eligible(self.phone, self.instance))

    @override_settings(COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=True)
    def test_modo_publico_aceita_contato_novo_sem_inserir_na_allowlist(self):
        self.assertTrue(eligible(self.phone, self.instance))
        self.assertFalse(CommercialPilotContact.objects.exists())
        row = self.inbound('publico-001')
        self.assertEqual(row.state, 'queued')
        self.assertFalse(CommercialPilotContact.objects.exists())

    @override_settings(COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=True)
    def test_modo_publico_responde_apenas_mensagem_recebida(self):
        row = self.inbound('publico-002')
        publication = {'fingerprint': 'catalogo-teste'}
        with (
            patch('apps.prospecting.commercial.published_catalog', return_value=publication),
            patch('apps.prospecting.commercial.articles', return_value=[object()]),
            patch('apps.prospecting.commercial.compose', return_value=('Resposta revisada', [1])),
            patch('apps.prospecting.commercial_greetings.enhance_reply', side_effect=lambda c, r, t: t),
            patch('apps.prospecting.commercial.TenantEvolutionClient') as evolution,
        ):
            evolution.return_value.status.return_value = 'open'
            evolution.return_value.send_text.return_value = 'aceito-pelo-provedor'
            process_message(row.pk)
            evolution.return_value.send_text.assert_called_once_with(
                self.instance, self.phone, 'Resposta revisada'
            )
        row.refresh_from_db()
        self.assertEqual(row.state, 'submitted')

    @override_settings(COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=True)
    def test_otp_excluido_impede_resposta_e_armazenamento_de_conversa(self):
        CommercialOtpExclusion.objects.create(instance=self.instance, phone=self.phone)
        self.assertFalse(eligible(self.phone, self.instance))
        self.assertIsNone(self.inbound('otp-protegido'))
        self.assertFalse(CommercialConversation.objects.exists())
        self.assertFalse(CommercialMessage.objects.exists())

    @override_settings(COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=True)
    def test_propria_mensagem_nao_inicia_resposta_automatica(self):
        row = self.inbound('from-me-001', text='Mensagem humana', from_me=True)
        self.assertEqual(row.state, 'human')
        with patch('apps.prospecting.commercial.TenantEvolutionClient') as evolution:
            process_message(row.pk)
            evolution.assert_not_called()

    @override_settings(COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=True)
    def test_defesa_para_erro_de_fila_com_mensagem_from_me(self):
        conv = CommercialConversation.objects.create(instance=self.instance, phone=self.phone)
        row = CommercialMessage.objects.create(
            conversation=conv, provider_id='from-me-in-queue', from_me=True,
            state='queued', text='Mensagem emitida pela própria instância',
        )
        with patch('apps.prospecting.commercial.TenantEvolutionClient') as evolution:
            process_message(row.pk)
            evolution.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.state, 'held')

    @override_settings(COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=True)
    def test_optout_nao_responde(self):
        row = self.inbound('publico-optout', text='Parar')
        self.assertEqual(row.state, 'human')
        row.conversation.refresh_from_db()
        self.assertTrue(row.conversation.opted_out)
        self.assertFalse(eligible(self.phone, None))

    @override_settings(COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=True)
    def test_numero_da_propria_empresa_nao_e_elegivel(self):
        with override_settings(MARKETING_WHATSAPP=self.phone):
            self.assertFalse(eligible(self.phone, self.instance))
            self.assertEqual(self.inbound('auto-numero').state, 'held')

    @override_settings(COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=True)
    def test_mensagens_antigas_retidas_nao_sao_reprocessadas(self):
        conv = CommercialConversation.objects.create(instance=self.instance, phone=self.phone)
        row = CommercialMessage.objects.create(
            conversation=conv, provider_id='retida-antiga', state='held', text='Oi',
        )
        with patch('apps.prospecting.commercial.TenantEvolutionClient') as evolution:
            process_message(row.pk)
            evolution.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.state, 'held')

    @override_settings(COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=True)
    def test_enable_publico_nao_exige_allowlist(self):
        self.control.enabled = False
        self.control.save(update_fields=['enabled'])
        with (
            patch('apps.prospecting.commercial_api.published_catalog'),
            patch('apps.prospecting.commercial_api.articles', return_value=[object()]),
            patch('apps.prospecting.commercial_api.TenantEvolutionClient') as evolution,
        ):
            evolution.return_value.status.return_value = 'open'
            response = CommercialPanel()._post_settings(SimpleNamespace(
                data={'action': 'enable', 'confirm_pilot': True}, user=None,
            ))
        self.assertEqual(response.status_code, 200)
        self.control.refresh_from_db()
        self.assertTrue(self.control.enabled)
        self.assertFalse(CommercialPilotContact.objects.exists())

    @override_settings(COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=True)
    def test_modo_publico_nao_altera_lista_do_piloto_pelo_painel(self):
        self.control.enabled = False
        self.control.save(update_fields=['enabled'])
        result = CommercialPanel()._post_settings(SimpleNamespace(
            data={'action': 'pilot_allow', 'phone': self.phone}, user=None,
        ))
        self.assertEqual(result.status_code, 400)
        self.assertFalse(CommercialPilotContact.objects.exists())
