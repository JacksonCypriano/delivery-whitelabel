import requests
from django.conf import settings

def enviar_mensagem_via_evolution(numero, texto, tenant):
    url = f"{settings.EVOLUTION_API_URL}/message/sendText/{tenant.whatsapp_instance_key}"
    headers = {
        'apikey': tenant.whatsapp_api_key or settings.EVOLUTION_API_KEY
    }
    data = {
        'number': numero,
        'text': texto
    }
    requests.post(url, headers=headers, json=data)
