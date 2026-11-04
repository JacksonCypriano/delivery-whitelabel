"""Signed 99Food sandbox webhook ingestion with fail-closed durable ACK.

The default is legacy 503 quarantine. An explicit, isolated pilot can ACK only
after an event has been durably committed; all payload storage is PII-free.
"""
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone as datetime_timezone

from django.conf import settings
from django.db import DatabaseError, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.channels.models import Connection, Inbox

MAX_BODY_BYTES = 131072
SIGNATURE_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
KNOWN_EVENTS = frozenset({
    "orderNew", "orderConfirm", "orderReady", "orderCancel",
    "orderPartialCancel", "orderFinish", "orderCancelApply",
    "orderRefundApply", "deliveryStatus", "shopBindStatus", "shopStatus",
    "imageAuditStatus", "autoOnlineResult", "uploadMenuTaskStatus",
})
# Only these event types have a documented, order-scoped identifier.
ORDER_EVENTS = frozenset({
    "orderNew", "orderConfirm", "orderReady", "orderCancel",
    "orderPartialCancel", "orderFinish", "orderCancelApply",
    "orderRefundApply", "deliveryStatus",
})
ORDER_ID = re.compile(r"^[0-9]{1,30}$")


def verify_signature(raw_body: bytes, header: str, app_secret: str) -> bool:
    """Use raw bytes; parse JSON only after signature validation."""
    if (not isinstance(raw_body, bytes) or not isinstance(header, str)
            or not SIGNATURE_PATTERN.fullmatch(header)
            or not isinstance(app_secret, str) or not app_secret):
        return False
    digest = hashlib.md5(raw_body + app_secret.encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, header.lower())


def _rejected(http_status: int, message: str):
    response = JsonResponse({"errno": 1, "errmsg": message}, status=http_status)
    response["Cache-Control"] = "no-store"
    if http_status == 503:
        response["Retry-After"] = "300"
    return response


def _order_id_from_event(event):
    """Parse JSON numbers using Python's lossless ints, store IDs as strings."""
    data = event.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (TypeError, ValueError):
            return None
    if not isinstance(data, dict):
        return None
    value = data.get("order_id")
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not ORDER_ID.fullmatch(value):
        return None
    nested = data.get("order_info")
    if isinstance(nested, dict) and "order_id" in nested:
        nested_id = nested["order_id"]
        if type(nested_id) is int:
            nested_id = str(nested_id)
        if nested_id != value:
            return None
    return value


def _store_order_event(connection, event, raw_body):
    """Durably quarantine only safe identifiers, not customer data or raw body.

    Identical retries produce the same sha256 key. Changing even one raw byte
    creates a separate observation; both remain visible for later reconciliation.
    """
    order_id = _order_id_from_event(event)
    if order_id is None:
        return False
    sha = hashlib.sha256(raw_body).hexdigest()
    external_id = "99food-" + sha  # 71 chars, fits Inbox.external_id
    with transaction.atomic():
        item, created = Inbox.objects.get_or_create(
            connection=connection,
            external_id=external_id,
            defaults={
                "order_id": order_id,
                "code": event["type"],
                "occurred_at": datetime.fromtimestamp(
                    event["timestamp"], tz=datetime_timezone.utc
                ),
                "payload": {
                    "food99_quarantined": True,
                    "raw_sha256": sha,
                    "app_shop_id": event["app_shop_id"],
                    "event_type": event["type"],
                    "operational_enabled": False,
                },
                "state": "blocked",
                "error": "Aguardando homologação do processamento 99Food.",
            },
        )
    return item, created


@csrf_exempt
@require_http_methods(["GET", "HEAD", "POST"])
def food99_webhook(request, mode):
    if mode != "test":
        return _rejected(404, "Indisponível.")

    if request.method in ("GET", "HEAD"):
        response = JsonResponse(
            {"provider": "99food", "mode": "test", "events_enabled": False},
            status=200,
        )
        response["Cache-Control"] = "no-store"
        if request.method == "HEAD":
            response.content = b""
        return response

    if (getattr(settings, "SETTINGS_MODULE", "") != "config.settings.hml"
            or not getattr(settings, "FOOD99_SANDBOX_ENABLED", False)
            or getattr(settings, "CHANNELS_LIVE_ENABLED", False)):
        return _rejected(404, "Indisponível.")

    if len(request.body) > MAX_BODY_BYTES:
        return _rejected(413, "Evento muito grande.")

    secret = getattr(settings, "FOOD99_TEST_APP_SECRET", "")
    signature = request.headers.get("didi-header-sign", "")
    if not verify_signature(request.body, signature, secret):
        return _rejected(401, "Assinatura inválida.")

    try:
        event = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return _rejected(400, "JSON inválido.")
    if not isinstance(event, dict):
        return _rejected(400, "Evento inválido.")

    app_id = getattr(settings, "FOOD99_TEST_APP_ID", "")
    event_app_id = event.get("app_id")
    if (not str(app_id).isdigit() or type(event_app_id) is not int
            or str(event_app_id) != str(app_id)):
        return _rejected(403, "Aplicativo não autorizado.")

    event_type = event.get("type")
    if not isinstance(event_type, str) or not event_type or len(event_type) > 100:
        return _rejected(400, "Tipo de evento inválido.")
    if (type(event.get("timestamp")) is not int
            or not 0 < event["timestamp"] < 253402300800
            or not isinstance(event.get("data"), (dict, str, list))):
        return _rejected(400, "Estrutura do evento inválida.")

    app_shop_id = event.get("app_shop_id")
    if (not isinstance(app_shop_id, str) or not app_shop_id
            or len(app_shop_id) > 255):
        return _rejected(503, "Evento aguardando integração.")

    tenant_slug = app_shop_id.removeprefix("vdd-") if app_shop_id.startswith("vdd-") else ""
    if not tenant_slug:
        return _rejected(403, "Estabelecimento não autorizado.")
    connections = list(Connection.objects.filter(
        provider="99food", mode="test", enabled=False,
        tenant__slug=tenant_slug,
    ).exclude(merchant_id__startswith="request-").order_by("pk")[:2])
    if len(connections) != 1:
        return _rejected(403, "Estabelecimento não autorizado.")

    if event_type not in KNOWN_EVENTS:
        return _rejected(503, "Tipo aguardando integração.")

    # Explicit, independent opt-ins. Legacy deployments still get a retryable
    # rejection; they never accidentally ACK an event because capture was enabled.
    ack_enabled = getattr(settings, "FOOD99_WEBHOOK_ACK_ENABLED", False) is True
    if ack_enabled and not (
        getattr(settings, "FOOD99_WEBHOOK_CAPTURE_ENABLED", False) is True
        and getattr(settings, "FOOD99_ASYNC_RECONCILE_ENABLED", False) is True
        and getattr(settings, "CHANNELS_NETWORK_ENABLED", False) is False
        and event_type in ORDER_EVENTS
    ):
        return _rejected(503, "Recebimento operacional não habilitado.")

    if (getattr(settings, "FOOD99_WEBHOOK_CAPTURE_ENABLED", False)
            and event_type in ORDER_EVENTS):
        try:
            stored = _store_order_event(connections[0], event, request.body)
            if not stored:
                return _rejected(400, "Identificador de pedido inválido.")
            item, created = stored
        except (DatabaseError, OverflowError, ValueError):
            return _rejected(503, "Armazenamento temporariamente indisponível.")

        if ack_enabled:
            # The Inbox is durable before response. A broker outage causes a
            # retryable 503, and an exact retransmission reuses the Inbox row.
            # The reconciliation command also recovers events not queued here.
            try:
                from .tasks import consume_99food_sandbox_event
                consume_99food_sandbox_event.delay(item.pk)
            except Exception:
                return _rejected(503, "Fila temporariamente indisponível.")
            response = JsonResponse({"errno": 0, "errmsg": "ok"}, status=200)
            response["Cache-Control"] = "no-store"
            return response

    return _rejected(503, "Evento aguardando processamento seguro.")
