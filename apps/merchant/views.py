import json
from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie


@never_cache
@ensure_csrf_cookie
def shell(request, path=""):
    if request.tenant is None:
        raise Http404("Loja não encontrada para este domínio.")
    manifest = settings.BASE_DIR / "static" / "merchant" / ".vite" / "manifest.json"
    if not manifest.exists():
        return HttpResponse(
            "Painel em preparação. O build do frontend ainda não foi instalado.",
            status=503,
        )
    entry = json.loads(manifest.read_text())["src/main.tsx"]
    return render(
        request,
        "merchant/shell.html",
        {
            "entry": entry["file"],
            "styles": entry.get("css", []),
            "panel_kind": "merchant",
            "panel_base": "/painel",
            "api_base": "/api/merchant/",
            "panel_title": "Painel da loja",
        },
    )
