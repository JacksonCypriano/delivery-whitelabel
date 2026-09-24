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


@csrf_exempt
@require_POST
@sensitive_post_parameters()
def tenant_evolution_webhook(request):
    """Authenticated webhook for tenant-owned WhatsApp instances."""
    expected = getattr(settings, "WHATSAPP_AGENT_WEBHOOK_TOKEN", "")
    supplied = request.headers.get("X-VDD-Webhook-Token", "")
    if (
        not getattr(settings, "WHATSAPP_AGENT_ENABLED", False)
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
        if not isinstance(payload, dict):
            return HttpResponse(status=400)
        instance_name = str(payload.get("instance") or "")[:100]
        if not instance_name:
            return HttpResponse(status=400)

        from .models import TenantWhatsAppAgent, TenantWhatsAppGroupNotice
        from .whatsapp_agent.connection import apply_connection_webhook, mark_pairing_hint
        from .whatsapp_agent.conversations import pause_for_manual_store_message
        from .whatsapp_agent.provider import (
            extract_group_message,
            extract_message,
            incoming_once,
            is_agent_outbound,
            normalize_event_name,
        )

        agent = (
            TenantWhatsAppAgent.objects.select_related("tenant")
            .filter(instance_name=instance_name, tenant__is_active=True)
            .first()
        )
        if not agent:
            return HttpResponse(status=204)

        event = normalize_event_name(payload.get("event"))
        data = payload.get("data")
        if not isinstance(data, dict):
            return HttpResponse(status=400)

        if event == "connection.update":
            apply_connection_webhook(agent, data)
            return HttpResponse(status=202)
        if event == "qrcode.updated":
            mark_pairing_hint(agent)
            return HttpResponse(status=202)
        if event != "messages.upsert":
            return HttpResponse(status=204)

        group_message = extract_group_message(data)
        if group_message:
            if group_message["from_me"] or not agent.ai_enabled:
                return HttpResponse(status=202)
            if TenantWhatsAppGroupNotice.objects.filter(
                tenant=agent.tenant, group_jid=group_message["group_jid"]
            ).exists():
                return HttpResponse(status=202)
            from .tasks import notify_tenant_whatsapp_group_once

            notify_tenant_whatsapp_group_once.delay(
                agent.pk, group_message["group_jid"]
            )
            return HttpResponse(status=202)

        message = extract_message(data)
        if not message:
            return HttpResponse(status=204)

        if message["from_me"]:
            if not is_agent_outbound(
                agent.instance_name,
                message["phone"],
                message["message_id"],
                message["text"],
            ):
                pause_for_manual_store_message(agent.tenant, message["phone"])
            return HttpResponse(status=202)

        if not incoming_once(agent.instance_name, message["message_id"]):
            return HttpResponse(status=202)

        from .tasks import process_tenant_whatsapp_message
        process_tenant_whatsapp_message.delay(
            agent.pk,
            message["message_id"],
            message["phone"],
            message["text"],
            message.get("kind", "text"),
        )
        return HttpResponse(status=202)
    except (ValueError, TypeError, UnicodeError):
        return HttpResponse(status=400)
    except Exception:
        return HttpResponse(status=503)
