"""CSRF-protected click endpoint for signed, non-personal contact references."""
from django.conf import settings
from django.core import signing
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_POST

from .acquisition import AD_FIELDS, record_click
from .marketing_views import _indexable


@require_POST
def record_whatsapp_click(request):
    if (not getattr(settings, "MARKETING_LEAD_TRACKING_ENABLED", False)
            or not _indexable(request)):
        raise Http404
    fields = {key: request.POST.get(key, "") for key in AD_FIELDS}
    fields["ga_client_id"] = request.POST.get("ga_client_id", "")
    try:
        record_click(
            token=request.POST.get("token", ""),
            cta=request.POST.get("cta", ""),
            consent=request.POST.get("consent", "") == "yes",
            attribution=fields,
        )
    except (signing.BadSignature, TypeError, ValueError):
        return JsonResponse({"error": "Referência inválida ou expirada."}, status=400)
    response = JsonResponse({"ok": True})
    response["Cache-Control"] = "no-store"
    return response
