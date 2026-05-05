# apps/whatsapp/views.py
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import json
import logging

from .services import processar_mensagem

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class WebhookView(View):
    def post(self, request):
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            logger.error("Falha ao decodificar JSON no webhook.")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        logger.warning(f"payload: {payload}")

        # tenant = getattr(request, 'tenant', None)
        # if not tenant:
        #     logger.warning("Tenant não encontrado no request.")
        #     return JsonResponse({'error': 'Tenant not found'}, status=400)

        # logger.info(f"[{tenant.slug}] Recebendo mensagem via webhook: {payload}")
        
        # logger.warning(f"payload: {payload}")
        # try:
        #     processar_mensagem(payload, tenant)
        # except Exception as e:
        #     logger.exception(f"[{tenant.slug}] Erro ao processar mensagem: {e}")
        #     return JsonResponse({'error': 'Internal processing error'}, status=500)

        return JsonResponse({'status': 'ok'})
