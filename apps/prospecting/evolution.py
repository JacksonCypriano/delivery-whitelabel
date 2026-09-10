from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from urllib import error, parse, request

from django.conf import settings


class EvolutionRejectedError(RuntimeError):
    """Falha explícita: a API/WhatsApp rejeitou o envio."""


class EvolutionNumberNotOnWhatsAppError(EvolutionRejectedError):
    """A Evolution confirmou que o número não existe no WhatsApp."""


class EvolutionReachoutRestrictedError(EvolutionRejectedError):
    """O WhatsApp recusou a abertura de nova conversa (código 463)."""


class EvolutionDeliveryUnknownError(RuntimeError):
    """Não foi possível confirmar ACK; não é seguro reenviar automaticamente."""


class EvolutionInstanceUnavailableError(RuntimeError):
    """A instância de prospecção não está pronta para envio."""


class _EvolutionHTTPError(RuntimeError):
    def __init__(self, code: int, body: bytes = b""):
        self.code = code
        self.body = body
        super().__init__(f"HTTP {code}")


class _EvolutionTransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvolutionSendReceipt:
    message_id: str
    remote_jid: str


SUCCESS_ACKS = {"SERVER_ACK", "DELIVERY_ACK", "READ", "PLAYED"}
FAILURE_ACKS = {"ERROR", "FAILED"}


def _setting(name: str, default=None):
    value = getattr(settings, name, None)
    if value not in (None, ""):
        return value
    return os.getenv(name, default)


def _bool_setting(name: str, default: bool) -> bool:
    value = _setting(name, None)
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _config():
    base_url = (_setting("EVOLUTION_API_URL", "") or "").rstrip("/")
    api_key = _setting("EVOLUTION_API_KEY", "") or ""
    instance = _setting("PROSPECTING_EVOLUTION_INSTANCE", "") or ""
    timeout = float(_setting("EVOLUTION_API_TIMEOUT", 20) or 20)
    if not base_url or not api_key or not instance:
        raise EvolutionInstanceUnavailableError(
            "Configuração da Evolution API de prospecção incompleta."
        )
    return base_url, api_key, instance, max(1.0, min(timeout, 30.0))


def _request_json(method: str, operation: str, payload=None):
    base_url, api_key, instance, timeout = _config()
    endpoint = f"{base_url}/{operation}/{parse.quote(instance, safe='')}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        endpoint,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept-Encoding": "identity",
            "apikey": api_key,
        },
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read(512_001)
            if len(body) > 512_000:
                raise _EvolutionTransportError("Resposta da Evolution excedeu o limite seguro.")
            if not body:
                return {}
            try:
                return json.loads(body.decode("utf-8", errors="replace"))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise _EvolutionTransportError("Resposta JSON inválida da Evolution.") from exc
    except error.HTTPError as exc:
        raise _EvolutionHTTPError(exc.code, exc.read(512_001) or b"") from exc
    except _EvolutionHTTPError:
        raise
    except (error.URLError, TimeoutError, OSError) as exc:
        raise _EvolutionTransportError("Falha de comunicação com a Evolution.") from exc


def get_prospecting_connection_state() -> str:
    try:
        data = _request_json("GET", "instance/connectionState")
    except (_EvolutionHTTPError, _EvolutionTransportError) as exc:
        raise EvolutionInstanceUnavailableError(
            "Não foi possível consultar a conexão da instância de prospecção."
        ) from exc

    instance = data.get("instance") if isinstance(data, dict) else None
    state = instance.get("state") if isinstance(instance, dict) else None
    if state not in {"open", "close", "connecting"}:
        raise EvolutionInstanceUnavailableError(
            "A Evolution devolveu um estado de conexão inválido."
        )
    return state


def restart_prospecting_instance() -> None:
    try:
        _request_json("PUT", "instance/restart")
    except (_EvolutionHTTPError, _EvolutionTransportError) as exc:
        raise EvolutionInstanceUnavailableError(
            "A Evolution não confirmou o comando de reconexão."
        ) from exc


def ensure_prospecting_instance_open() -> str:
    """Garante conexão antes de tocar na fila; reconecta automaticamente se caiu."""
    state = get_prospecting_connection_state()
    if state == "open":
        return "open"

    auto_reconnect = _bool_setting("PROSPECTING_EVOLUTION_AUTO_RECONNECT", True)
    wait_seconds = float(_setting("PROSPECTING_EVOLUTION_RECONNECT_WAIT_SECONDS", 10) or 10)
    wait_seconds = max(0.0, min(wait_seconds, 20.0))

    if state == "close" and auto_reconnect:
        restart_prospecting_instance()

    # Se a Evolution já está connecting, não dispara restart concorrente. Apenas
    # aguarda a sessão terminar de subir; no próximo Beat a verificação continua.
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(min(1.0, max(0.05, wait_seconds)))
        try:
            state = get_prospecting_connection_state()
        except EvolutionInstanceUnavailableError:
            continue
        if state == "open":
            return "reconnected"
        if state == "close" and not auto_reconnect:
            break

    raise EvolutionInstanceUnavailableError(
        "Instância de prospecção ainda não está conectada."
    )


def _digits(value) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


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

    normalized_phone = _digits(phone)
    for item in messages:
        if not isinstance(item, dict) or item.get("exists") is not False:
            continue
        returned_number = _digits(item.get("number"))
        if not returned_number or returned_number == normalized_phone:
            return True
    return False


def resolve_whatsapp_number(phone: str) -> str:
    """Retorna o número canônico do JID confirmado pelo próprio WhatsApp."""
    normalized_phone = _digits(phone)
    try:
        payload = _request_json(
            "POST", "chat/whatsappNumbers", {"numbers": [normalized_phone]}
        )
    except _EvolutionHTTPError as exc:
        if _response_says_number_does_not_exist(exc.body, normalized_phone):
            raise EvolutionNumberNotOnWhatsAppError(
                "A Evolution confirmou que o número não existe no WhatsApp."
            ) from exc
        raise EvolutionRejectedError(
            f"Evolution rejeitou a validação do número (HTTP {exc.code})."
        ) from exc
    except _EvolutionTransportError as exc:
        # A falha ocorreu antes do POST de envio; portanto não existe risco de
        # duplicidade. Trate como rejeição operacional e libere o lead.
        raise EvolutionRejectedError(
            "Não foi possível validar o número na Evolution."
        ) from exc

    rows = payload
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("users") or payload.get("Users") or []
    if not isinstance(rows, list):
        raise EvolutionRejectedError("Resposta inválida ao validar número no WhatsApp.")

    for row in rows:
        if not isinstance(row, dict):
            continue
        returned_number = _digits(row.get("number"))
        if returned_number and returned_number != normalized_phone:
            continue
        if row.get("exists") is False or row.get("IsInWhatsapp") is False:
            raise EvolutionNumberNotOnWhatsAppError(
                "A Evolution confirmou que o número não existe no WhatsApp."
            )
        exists = row.get("exists", row.get("IsInWhatsapp"))
        if exists is not True:
            continue
        jid = str(row.get("jid") or row.get("Jid") or "")
        canonical = _digits(jid.split("@", 1)[0])
        if canonical:
            return canonical

    raise EvolutionNumberNotOnWhatsAppError(
        "A Evolution não confirmou esse número como conta WhatsApp."
    )


def _records(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    messages = payload.get("messages", payload)
    if isinstance(messages, list):
        return messages
    if isinstance(messages, dict):
        records = messages.get("records")
        return records if isinstance(records, list) else []
    return []


def _walk_statuses_and_stubs(value, statuses: list, stubs: list) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "status":
                statuses.append(item)
            elif key == "messageStubParameters" and isinstance(item, list):
                stubs.extend(str(parameter) for parameter in item)
            else:
                _walk_statuses_and_stubs(item, statuses, stubs)
    elif isinstance(value, list):
        for item in value:
            _walk_statuses_and_stubs(item, statuses, stubs)


def _confirmation_state(payload, message_id: str) -> str:
    for record in _records(payload):
        if not isinstance(record, dict):
            continue
        key = record.get("key")
        if not isinstance(key, dict) or str(key.get("id") or "") != message_id:
            continue

        statuses = []
        stubs = []
        _walk_statuses_and_stubs(record, statuses, stubs)
        if "463" in stubs:
            return "reachout-restricted"

        normalized = {str(status).upper() for status in statuses if status is not None}
        numeric = {int(status) for status in statuses if isinstance(status, int)}
        if normalized & SUCCESS_ACKS or numeric & {2, 3, 4, 5}:
            return "confirmed"
        if normalized & FAILURE_ACKS or 0 in numeric:
            return "rejected"
        return "pending"
    return "pending"


def wait_for_message_confirmation(message_id: str) -> None:
    ack_timeout = float(_setting("PROSPECTING_EVOLUTION_ACK_TIMEOUT", 5) or 5)
    ack_timeout = max(0.5, min(ack_timeout, 15.0))
    deadline = time.monotonic() + ack_timeout

    while True:
        try:
            payload = _request_json(
                "POST",
                "chat/findMessages",
                {"where": {"key": {"id": message_id}}},
            )
        except (_EvolutionHTTPError, _EvolutionTransportError) as exc:
            raise EvolutionDeliveryUnknownError(
                "A Evolution aceitou o envio, mas o ACK não pôde ser consultado."
            ) from exc

        state = _confirmation_state(payload, message_id)
        if state == "confirmed":
            return
        if state == "reachout-restricted":
            raise EvolutionReachoutRestrictedError(
                "WhatsApp recusou abertura de nova conversa (código 463)."
            )
        if state == "rejected":
            raise EvolutionRejectedError(
                "WhatsApp rejeitou a mensagem após a aceitação inicial."
            )
        if time.monotonic() >= deadline:
            # A Evolution retorna PENDING imediatamente após um sendText aceito
            # e os ACKs seguintes podem chegar depois da janela de polling. Se
            # conseguimos consultar a mensagem sem rejeição explícita, não
            # pausamos a fila apenas por ela ainda estar PENDING. A trava global
            # por telefone continua impedindo uma segunda abordagem.
            return
        time.sleep(0.5)


def send_prospecting_text(phone: str, text: str) -> EvolutionSendReceipt:
    canonical_number = resolve_whatsapp_number(phone)

    try:
        payload = _request_json(
            "POST",
            "message/sendText",
            {"number": canonical_number, "text": text},
        )
    except _EvolutionHTTPError as exc:
        if _response_says_number_does_not_exist(exc.body, canonical_number):
            raise EvolutionNumberNotOnWhatsAppError(
                "A Evolution confirmou que o número não existe no WhatsApp."
            ) from exc
        raise EvolutionRejectedError(
            f"Evolution rejeitou o envio (HTTP {exc.code})."
        ) from exc
    except _EvolutionTransportError as exc:
        raise EvolutionDeliveryUnknownError(
            "Não foi possível confirmar a entrega na Evolution."
        ) from exc

    key = payload.get("key") if isinstance(payload, dict) else None
    message_id = str(key.get("id") or "") if isinstance(key, dict) else ""
    remote_jid = str(key.get("remoteJid") or "") if isinstance(key, dict) else ""
    if not message_id or not remote_jid:
        raise EvolutionDeliveryUnknownError(
            "Evolution aceitou o request sem devolver identificação confiável da mensagem."
        )

    # HTTP 200/201 e PENDING não significam envio real. Só retorna sucesso
    # depois de SERVER_ACK (ou estágio posterior) registrado pela Evolution.
    wait_for_message_confirmation(message_id)
    return EvolutionSendReceipt(message_id=message_id, remote_jid=remote_jid)
