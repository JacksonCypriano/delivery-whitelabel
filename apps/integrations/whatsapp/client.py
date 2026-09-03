"""Fixed Evolution endpoints only. Never expose response bodies or API credentials."""

import time
from urllib.parse import quote, urlsplit

import requests
from django.conf import settings
from django.views.decorators.debug import sensitive_variables


class EvolutionError(Exception):
    def __init__(self, reason="unavailable"):
        self.reason = reason
        super().__init__("Integração WhatsApp indisponível.")


class EvolutionClient:
    @sensitive_variables()
    def request(self, method, operation, payload=None):
        base = settings.EVOLUTION_API_URL.rstrip("/")
        instance = settings.EVOLUTION_INSTANCE
        parsed = urlsplit(base)
        if (
            not settings.EVOLUTION_API_KEY
            or not instance
            or not parsed.hostname
            or parsed.scheme not in {"http", "https"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise EvolutionError("configuration")
        if operation not in {
            "message/sendText",
            "chat/whatsappNumbers",
            "instance/connectionState",
            "instance/restart",
            "instance/connect",
        }:
            raise EvolutionError("configuration")
        url = f"{base}/{operation}/{quote(instance, safe='')}"
        timeout = max(1, min(settings.EVOLUTION_API_TIMEOUT, 10))
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.request(
                    method,
                    url,
                    headers={
                        "apikey": settings.EVOLUTION_API_KEY,
                        "Accept-Encoding": "identity",
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
                    if response.status_code != 200 and response.status_code != 201:
                        raise EvolutionError("unavailable")
                    content = bytearray()
                    started = time.monotonic()
                    for chunk in response.iter_content(8192):
                        content.extend(chunk)
                        if len(content) > 512_000 or time.monotonic() - started > 20:
                            raise EvolutionError("invalid_response")
                    import json

                    result = json.loads(content)
                    if not isinstance(result, (dict, list)):
                        raise EvolutionError("invalid_response")
                    return result
        except EvolutionError:
            raise
        except (requests.RequestException, ValueError, TypeError):
            raise EvolutionError("unavailable") from None

    def status(self):
        data = self.request("GET", "instance/connectionState")
        instance = data.get("instance") if isinstance(data, dict) else None
        if (
            not isinstance(instance, dict)
            or instance.get("instanceName") != settings.EVOLUTION_INSTANCE
        ):
            raise EvolutionError("invalid_response")
        state = instance.get("state")
        if state not in {"open", "close", "connecting"}:
            raise EvolutionError("invalid_response")
        return state

    def restart(self):
        # Restart preserves the session; logout/delete are deliberately unsupported.
        self.request("PUT", "instance/restart")

    def connect(self):
        return self.request("GET", "instance/connect")

    @sensitive_variables("text", "data")
    def send_text(self, number, text):
        data = self.request(
            "POST", "message/sendText", {"number": number, "text": text}
        )
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("key"), dict)
            or not data["key"].get("id")
        ):
            raise EvolutionError("invalid_response")


class OTPTransport:
    """Transport boundary, not verification policy. E-mail never verifies a phone."""

    def send_phone_code(self, number, text):
        EvolutionClient().send_text(number, text)


def phone_otp_transport():
    return OTPTransport()
