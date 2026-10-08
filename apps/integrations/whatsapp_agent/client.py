"""Evolution client dedicated to tenant-owned WhatsApp instances.

The platform OTP/prospecting instance continues using apps.integrations.whatsapp.client.
No provider response body or credential is logged.
"""

import json
import secrets
import time
from urllib.parse import quote, urlsplit

import requests
from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from apps.integrations.whatsapp.client import EvolutionError


class TenantEvolutionClient:
    def _base(self):
        base = settings.EVOLUTION_API_URL.rstrip("/")
        parsed = urlsplit(base)
        if (
            not settings.EVOLUTION_API_KEY
            or not parsed.hostname
            or parsed.scheme not in {"http", "https"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise EvolutionError("configuration")
        return base

    @sensitive_variables("payload")
    def _request(self, method, path, payload=None, *, max_bytes=512_000):
        url = f"{self._base()}/{path.lstrip('/')}"
        timeout = max(1, min(int(settings.EVOLUTION_API_TIMEOUT), 10))
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.request(
                    method,
                    url,
                    headers={
                        "apikey": settings.EVOLUTION_API_KEY,
                        "Accept-Encoding": "identity",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=(timeout, timeout),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    if response.status_code in (401, 403):
                        raise EvolutionError("credentials")
                    if response.status_code == 404:
                        raise EvolutionError("not_found")
                    if response.status_code == 429:
                        raise EvolutionError("rate_limit")
                    if response.status_code not in (200, 201):
                        raise EvolutionError("unavailable")
                    content = bytearray()
                    started = time.monotonic()
                    for chunk in response.iter_content(8192):
                        content.extend(chunk)
                        if len(content) > max_bytes or time.monotonic() - started > 20:
                            raise EvolutionError("invalid_response")
                    if not content:
                        return {}
                    result = json.loads(content)
                    if not isinstance(result, (dict, list)):
                        raise EvolutionError("invalid_response")
                    return result
        except EvolutionError:
            raise
        except (requests.RequestException, ValueError, TypeError):
            raise EvolutionError("unavailable") from None

    def create(self, instance_name):
        webhook_url = settings.WHATSAPP_AGENT_WEBHOOK_URL.strip()
        webhook_token = settings.WHATSAPP_AGENT_WEBHOOK_TOKEN.strip()
        parsed = urlsplit(webhook_url)
        if (
            not settings.WHATSAPP_AGENT_ENABLED
            or len(webhook_token) < 32
            or not parsed.hostname
            or parsed.scheme not in {"http", "https"}
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise EvolutionError("configuration")

        # Token exists only on the provider side. Management calls keep using the
        # global API key, so tenant credentials are never persisted in our DB.
        provider_token = secrets.token_hex(24)
        return self._request(
            "POST",
            "instance/create",
            {
                "instanceName": instance_name,
                "token": provider_token,
                "qrcode": True,
                "integration": "WHATSAPP-BAILEYS",
                "rejectCall": True,
                "groupsIgnore": False,
                "alwaysOnline": False,
                "readMessages": False,
                "readStatus": False,
                "syncFullHistory": False,
                "webhook": {
                    "enabled": True,
                    "url": webhook_url,
                    "headers": {"X-VDD-Webhook-Token": webhook_token},
                    "byEvents": False,
                    "base64": False,
                    "events": [
                        "QRCODE_UPDATED",
                        "MESSAGES_UPSERT",
                        "CONNECTION_UPDATE",
                    ],
                },
            },
        )

    def set_agent_settings(self, instance_name):
        return self._request(
            "POST",
            f"settings/set/{quote(instance_name, safe='')}",
            {
                "rejectCall": True,
                "msgCall": "Envie uma mensagem por texto e a loja continua o atendimento por aqui.",
                "groupsIgnore": False,
                "alwaysOnline": False,
                "readMessages": False,
                "readStatus": False,
                "syncFullHistory": False,
            },
        )

    def status(self, instance_name):
        data = self._request(
            "GET", f"instance/connectionState/{quote(instance_name, safe='')}"
        )
        instance = data.get("instance") if isinstance(data, dict) else None
        if not isinstance(instance, dict):
            raise EvolutionError("invalid_response")
        returned_name = instance.get("instanceName")
        if returned_name and returned_name != instance_name:
            raise EvolutionError("invalid_response")
        state = instance.get("state")
        if state not in {"open", "close", "connecting"}:
            raise EvolutionError("invalid_response")
        return state

    def restart(self, instance_name):
        self._request("PUT", f"instance/restart/{quote(instance_name, safe='')}")

    def connect(self, instance_name):
        return self._request(
            "GET", f"instance/connect/{quote(instance_name, safe='')}"
        )

    def logout(self, instance_name):
        return self._request(
            "DELETE", f"instance/logout/{quote(instance_name, safe='')}"
        )

    @sensitive_variables("text")
    def send_text(self, instance_name, number, text):
        from .provider import mark_outbound_message, mark_outbound_pending
        remaining = str(text)
        message_id = ""
        while remaining:
            if len(remaining) > 3500:
                cut = remaining.rfind("\n", 0, 3500)
                cut = cut if cut > 0 else 3500
            else:
                cut = len(remaining)
            chunk, remaining = remaining[:cut], remaining[cut:].lstrip("\n")
            mark_outbound_pending(instance_name, number, chunk)
            data = self._request("POST", f"message/sendText/{quote(instance_name, safe='')}", {"number": number, "text": chunk})
            message_id = self._message_id(data)
            mark_outbound_message(instance_name, message_id)
        if not message_id:
            raise EvolutionError("invalid_response")
        return message_id

    def send_choices(self, instance_name, number, choices):
        """Optional enhancement; the preceding text always contains every choice."""
        if len(choices) <= 3:
            path = "sendButtons"
            payload = {"number": number, "title": "Escolha uma opção", "description": "Você também pode responder pelo número.", "footer": "VemDeDelivery", "buttons": [{"type": "reply", "displayText": label[:20], "id": key} for key, label in choices]}
        else:
            path = "sendList"
            payload = {"number": number, "title": "Opções do pedido", "description": "Escolha uma opção", "buttonText": "Ver opções", "footerText": "VemDeDelivery", "sections": [{"title": "Opções", "rows": [{"title": label[:24], "description": label[:72], "rowId": key} for key, label in choices[:10]]}]}
        data = self._request("POST", f"message/{path}/{quote(instance_name, safe='')}", payload)
        return self._message_id(data)

    @staticmethod
    def _message_id(data):
        if not isinstance(data, dict) or not isinstance(data.get("key"), dict) or not data["key"].get("id"):
            raise EvolutionError("invalid_response")
        return str(data["key"]["id"])

    def send_pix_image(self, instance_name, number, encoded_image):
        data = self._request("POST", f"message/sendMedia/{quote(instance_name, safe='')}", {"number": number, "mediatype": "image", "mimetype": "image/png", "caption": "Pix do seu pedido — aguardando pagamento", "media": encoded_image, "fileName": "pix-pedido.png"})
        return self._message_id(data)
