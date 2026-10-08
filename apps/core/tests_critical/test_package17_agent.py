from unittest.mock import patch
from django.test import Client, override_settings
from django.utils import timezone
from apps.integrations.models import TenantWhatsAppConversation, TenantWhatsAppAgent
from apps.integrations.whatsapp_agent.conversations import pause
from apps.integrations.whatsapp_agent.media import interpret, MediaUnavailable
from apps.integrations.tasks import process_tenant_whatsapp_message
from .base import CriticalTestCase

class AdvancedAgentTests(CriticalTestCase):
    def setUp(self):
        self.client=Client(HTTP_HOST=self.host(self.tenant_a));self.client.force_login(self.admin_a)
        self.agent=TenantWhatsAppAgent.objects.create(tenant=self.tenant_a,instance_name='advanced',ai_enabled=True)
        self.conversation=TenantWhatsAppConversation.objects.create(tenant=self.tenant_a,phone_number='5511987654321',context={'product_id':self.product_a.pk},context_updated_at=timezone.now())

    def test_handoff_retains_context_for_operator(self):
        pause(self.tenant_a,self.conversation.phone_number,60,'human')
        self.assertEqual(self.conversation.entries.get(role='handoff').context['product_id'],self.product_a.pk)
        self.assertEqual(self.client.get('/api/merchant/conversations/').json()['conversations'][0]['id'],self.conversation.pk)

    def test_resume_and_tenant_isolation(self):
        pause(self.tenant_a,self.conversation.phone_number,60,'human')
        path='/api/merchant/conversations/'
        self.assertEqual(self.client.post(path,{'id':self.conversation.pk,'action':'resume'},content_type='application/json').status_code,200)
        self.conversation.refresh_from_db();self.assertFalse(self.conversation.is_paused)
        other=TenantWhatsAppConversation.objects.create(tenant=self.tenant_b,phone_number='5511888888888')
        self.assertEqual(self.client.post(path,{'id':other.pk,'action':'resume'},content_type='application/json').status_code,404)

    def test_media_disabled_without_credentials(self):
        with self.assertRaises(MediaUnavailable):interpret(self.agent,'msg',self.conversation.phone_number,'audio')

    @override_settings(WHATSAPP_AGENT_ENABLED=True,WHATSAPP_MEDIA_ENABLED=True,WHATSAPP_AGENT_CHECKOUT_ENABLED=False)
    def test_audio_continues_same_agent(self):
        with patch('apps.integrations.whatsapp_agent.media.interpret',return_value='qual o endereço?'),patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text',return_value='sent') as send:
            result=process_tenant_whatsapp_message(self.agent.pk,'audio1',self.conversation.phone_number,'','audio')
            self.assertTrue(result.startswith('answered:'));send.assert_called_once()
            self.assertEqual(self.conversation.entries.get(key='media:audio1').text,'qual o endereço?')

    @override_settings(WHATSAPP_AGENT_ENABLED=True,WHATSAPP_MEDIA_ENABLED=True)
    def test_media_failure_handoff_never_calls_payment(self):
        with patch('apps.integrations.whatsapp_agent.media.interpret',side_effect=MediaUnavailable),patch('apps.integrations.whatsapp_agent.checkout.handle_checkout') as checkout:
            result=process_tenant_whatsapp_message(self.agent.pk,'image1',self.conversation.phone_number,'','image')
            self.assertEqual(result,'media-handoff');checkout.assert_not_called()
            self.conversation.refresh_from_db();self.assertTrue(self.conversation.is_paused)

    @override_settings(WHATSAPP_AGENT_ENABLED=True,WHATSAPP_MEDIA_ENABLED=True)
    def test_image_never_executes_checkout(self):
        with patch('apps.integrations.whatsapp_agent.media.interpret',return_value='Vocês têm pizza?'),patch('apps.integrations.whatsapp_agent.checkout.handle_checkout') as checkout,patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text',return_value='sent'):
            process_tenant_whatsapp_message(self.agent.pk,'image2',self.conversation.phone_number,'','image');checkout.assert_not_called()
