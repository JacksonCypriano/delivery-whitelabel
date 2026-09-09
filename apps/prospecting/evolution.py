from __future__ import annotations

import json
import os
from urllib import error, parse, request

from django.conf import settings


class EvolutionRejectedError(RuntimeError):
    """Falha explícita: a API rejeitou o envio."""


class EvolutionNumberNotOnWhatsAppError(EvolutionRejectedError):
    """A Evolution confirmou que o número não existe no WhatsApp."""


class EvolutionDeliveryUnknownError(RuntimeError):
    """Falha de rede/timeout: não é seguro afirmar se houve entrega."""


def _setting(name: str, default=None):
    value = getattr(settings, name, None)
    if value not in (None, ""):
        return value
    return os.getenv(name, default)


def _response_says_number_does_not_exist(body: bytes, phone: str) -> bool:
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False

    if not isinstance(payload, dict):
        return False

    response = payload.get("response")
    if not isinstance(response, dict):
        return False

    messages = response.get("message")
    if not isinstance(messages, list):
        return False

    normalized_phone = "".join(char for char in str(phone) if char.isdigit())
    for item in messages:
        if not isinstance(item, dict) or item.get("exists") is not False:
            continue
        returned_number = "".join(char for char in str(item.get("number") or "") if char.isdigit())
        if not returned_number or returned_number == normalized_phone:
            return True

    return False


def send_prospecting_text(phone: str, text: str) -> None:
    base_url = (_setting("EVOLUTION_API_URL", "") or "").rstrip("/")
    api_key = _setting("EVOLUTION_API_KEY", "") or ""
    instance = _setting("PROSPECTING_EVOLUTION_INSTANCE", "") or ""
    timeout = float(_setting("EVOLUTION_API_TIMEOUT", 20) or 20)

    if not base_url or not api_key or not instance:
        raise EvolutionRejectedError("Configuração da Evolution API de prospecção incompleta.")

    endpoint = f"{base_url}/message/sendText/{parse.quote(instance, safe='')}"
    payload = json.dumps(
        {
            "number": phone,
            "text": text,
        }
    ).encode("utf-8")

    req = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "apikey": api_key},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise EvolutionRejectedError(f"Evolution rejeitou o envio (HTTP {response.status}).")
    except error.HTTPError as exc:
        # Quando a Evolution devolve exists=false, o número foi validado e não
        # pertence ao WhatsApp. Esse caso pode ser descartado sem consumir uma
        # vaga do limite de mensagens enviadas por minuto.
        body = exc.read() or b""
        if _response_says_number_does_not_exist(body, phone):
            raise EvolutionNumberNotOnWhatsAppError(
                "A Evolution confirmou que o número não existe no WhatsApp."
            ) from exc
        # Outros erros HTTP podem indicar configuração, autenticação ou outra
        # rejeição operacional. Não os confunda com número sem WhatsApp.
        raise EvolutionRejectedError(f"Evolution rejeitou o envio (HTTP {exc.code}).") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        # Timeout/erro de rede é ambíguo: a mensagem pode ter sido aceita antes da falha.
        raise EvolutionDeliveryUnknownError("Não foi possível confirmar a entrega na Evolution.") from exc
