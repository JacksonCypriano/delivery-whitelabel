from __future__ import annotations

import json
import os
from urllib import error, parse, request

from django.conf import settings


class EvolutionRejectedError(RuntimeError):
    """Falha explícita: a API rejeitou o envio."""


class EvolutionDeliveryUnknownError(RuntimeError):
    """Falha de rede/timeout: não é seguro afirmar se houve entrega."""


def _setting(name: str, default=None):
    value = getattr(settings, name, None)
    if value not in (None, ""):
        return value
    return os.getenv(name, default)


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
            "textMessage": {"text": text},
            "linkPreview": False,
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
        # Erro HTTP é uma rejeição explícita: a chamada chegou ao servidor.
        raise EvolutionRejectedError(f"Evolution rejeitou o envio (HTTP {exc.code}).") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        # Timeout/erro de rede é ambíguo: a mensagem pode ter sido aceita antes da falha.
        raise EvolutionDeliveryUnknownError("Não foi possível confirmar a entrega na Evolution.") from exc
