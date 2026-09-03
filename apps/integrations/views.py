"""Machine endpoint only; no status or administrative data in responses."""

import json
import secrets

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from .whatsapp.monitor import enabled, receive_hint, identity


@csrf_exempt
@require_POST
@sensitive_post_parameters()
def evolution_webhook(request):
    expected = settings.EVOLUTION_WEBHOOK_TOKEN
    supplied = request.headers.get("X-Evolution-Webhook-Token", "")
    if (
        not enabled()
        or len(expected) < 32
        or not secrets.compare_digest(expected, supplied)
    ):
        return HttpResponse(status=403)
    try:
        if int(request.META.get("CONTENT_LENGTH", 0) or 0) > 262144:
            return HttpResponse(status=413)
        raw = request.read(262145)
        if len(raw) > 262144:
            return HttpResponse(status=413)
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or payload.get("instance") != settings.EVOLUTION_INSTANCE
        ):
            return HttpResponse(status=400)
        kind = str(payload.get("event", "")).lower().replace("_", ".")
        if kind not in {"connection.update", "qrcode.updated"}:
            return HttpResponse(status=204)
        data = payload.get("data", {})
        if not isinstance(data, dict):
            return HttpResponse(status=400)
        if kind == "connection.update" and data.get("state") not in {
            "open",
            "close",
            "connecting",
        }:
            return HttpResponse(status=400)
        # Separate dedup keys ensure QR/session-invalid evidence isn't lost
        # behind a preceding ordinary connection event. No body is stored.
        pairing = kind == "qrcode.updated" or (
            data.get("state") == "close" and str(data.get("statusReason")) == "401"
        )
        key = f"evolution:hook:{identity()}:{int(pairing)}"
        if not cache.add(key, 1, timeout=15):
            return HttpResponse(status=202)
        receive_hint(pairing)
    except (ValueError, TypeError, UnicodeError):
        return HttpResponse(status=400)
    except Exception:
        # Provider retries. Periodic polling remains the independent recovery path.
        return HttpResponse(status=503)
    try:
        from .tasks import monitor_whatsapp

        monitor_whatsapp.delay()
    except Exception:
        pass  # State is durable; Beat will poll even if broker was down.
    return HttpResponse(status=202)
