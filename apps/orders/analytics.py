import hashlib
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import FunnelEvent


@require_POST
def event(request):
    if not getattr(request, "tenant", None):
        return JsonResponse({"error": "Loja não encontrada."}, status=404)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Dados inválidos."}, status=400)
    if not isinstance(data, dict) or data.get("consent") is not True:
        return JsonResponse({"error": "Consentimento necessário."}, status=400)
    stage = data.get("stage")
    if stage not in ("visit", "product", "cart", "checkout"):
        return JsonResponse({"error": "Etapa inválida."}, status=400)
    if not request.session.session_key:
        request.session.create()
    key = hashlib.sha256(
        (str(request.tenant.pk) + ":" + request.session.session_key).encode()
    ).hexdigest()
    FunnelEvent.objects.get_or_create(tenant=request.tenant, session=key, stage=stage)
    source = data.get("source", {})
    if isinstance(source, dict) and any(
        source.get(k) for k in ("utm_source", "utm_medium", "utm_campaign")
    ):
        request.session["order_attribution"] = {
            "tenant": request.tenant.pk,
            **{
                k: str(source.get(k, ""))[:180]
                for k in (
                    "utm_source",
                    "utm_medium",
                    "utm_campaign",
                    "utm_content",
                    "utm_term",
                )
            },
        }
    return JsonResponse({"ok": True})
