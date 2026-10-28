"""Public 99Food test-application webhook endpoint, not an event adapter.

Registration can confirm the HTTPS URL exists. POST deliberately fails closed
until the application's official signature and event contracts are implemented.
Never acknowledge an unverified event: a 2xx could cause permanent loss.
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@csrf_exempt
@require_http_methods(["GET", "HEAD", "POST"])
def food99_webhook(request, mode):
    # Production and simulation are intentionally not accessible as webhooks.
    if mode != "test":
        return JsonResponse({"detail": "Indisponível."}, status=404)

    if request.method in ("GET", "HEAD"):
        response = JsonResponse(
            {"provider": "99food", "mode": "test", "events_enabled": False},
            status=200,
        )
        response["Cache-Control"] = "no-store"
        if request.method == "HEAD":
            response.content = b""
        return response

    # The 99Food authentication/signature and message schema MUST be taken from
    # the official application's YAML before processing any external POST.
    # Do not save untrusted provider PII or return a false successful ACK.
    if len(request.body) > 131072:
        return JsonResponse({"detail": "Evento muito grande."}, status=413)
    response = JsonResponse(
        {"detail": "Webhook 99Food ainda não habilitado para receber eventos."},
        status=503,
    )
    response["Retry-After"] = "300"
    response["Cache-Control"] = "no-store"
    return response
