from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .services import processar_mensagem
import json

@method_decorator(csrf_exempt, name='dispatch')
class WebhookView(View):
    def post(self, request):
        payload = json.loads(request.body)
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return JsonResponse({'error': 'tenant not found'}, status=400)

        processar_mensagem(payload, tenant)
        return JsonResponse({'status': 'ok'})
