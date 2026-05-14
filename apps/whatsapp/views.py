import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from .selectors import get_config_by_phone_number_id
from .services import processar_mensagem_oficial
from .tasks import processar_mensagem_task

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class WhatsAppWebhookView(View):
    def get(self, request, *args, **kwargs):
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        verify_token = getattr(settings, 'WHATSAPP_WEBHOOK_VERIFY_TOKEN', None)

        if mode == 'subscribe' and token == verify_token:
            logger.info("Webhook validado com sucesso!")
            return HttpResponse(challenge)
        
        logger.warning(f"Falha na validação do webhook. Recebido: {token}")
        return HttpResponse("Token de verificação inválido", status=403)

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception as e:
            return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

        entry = payload.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        metadata = value.get('metadata', {})
        phone_number_id = metadata.get('phone_number_id')

        if not phone_number_id:
            return JsonResponse({"status": "ignored", "reason": "no_phone_number_id"})

        config = get_config_by_phone_number_id(phone_number_id)
        if not config or not config.tenant:
            logger.error(f"Configuração não encontrada para phone_number_id: {phone_number_id}")
            return JsonResponse({"status": "error", "reason": "tenant_not_found"}, status=404)

        messages = value.get('messages')
        if messages:
            for message in messages:
                processar_mensagem_task.delay(
                    config.tenant.id,
                    config.id,
                    message
                )

        return JsonResponse({"status": "success"})
