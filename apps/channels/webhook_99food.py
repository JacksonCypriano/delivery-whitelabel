"""99Food callback gate: validate the documented signature without acknowledging
unpersisted events. No order import, commands, payment, inventory, or notifications.

The legacy callback contract specifies MD5(raw POST body + app secret) in
'didi-header-sign'. Never print the body, headers, app secret, or exceptions.
"""

import hashlib
import hmac
import json
import re

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.channels.models import Connection

MAX_BODY_BYTES = 131072
SIGNATURE_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
KNOWN_EVENTS = frozenset({
    "orderNew", "orderConfirm", "orderReady", "orderCancel",
    "orderPartialCancel", "orderFinish", "orderCancelApply",
    "orderRefundApply", "deliveryStatus", "shopBindStatus", "shopStatus",
    "imageAuditStatus", "autoOnlineResult", "uploadMenuTaskStatus",
})


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

    # The gate remains unavailable outside HML, even with matching credentials.
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
            or not isinstance(event.get("data"), (dict, str, list))):
        return _rejected(400, "Estrutura do evento inválida.")

    app_shop_id = event.get("app_shop_id")
    if (not isinstance(app_shop_id, str) or not app_shop_id
            or len(app_shop_id) > 255):
        # Certain global callbacks may omit the store. Do not acknowledge them
        # until a separate app-level durable event pipeline is implemented.
        return _rejected(503, "Evento aguardando integração.")

    # Do not trust a provider-supplied shop ID as tenant identity. Require an
    # existing, disabled test connection belonging to the internal tenant slug.
    tenant_slug = app_shop_id.removeprefix("vdd-") if app_shop_id.startswith("vdd-") else ""
    if not tenant_slug or not Connection.objects.filter(
        provider="99food", mode="test", enabled=False,
        tenant__slug=tenant_slug,
    ).exclude(merchant_id__startswith="request-").exists():
        return _rejected(403, "Estabelecimento não autorizado.")

    if event_type not in KNOWN_EVENTS:
        return _rejected(503, "Tipo aguardando integração.")

    # No storage adapter is installed yet. A successful ACK here would tell
    # 99Food to stop retrying and could silently drop an order.
    return _rejected(503, "Evento aguardando processamento seguro.")
