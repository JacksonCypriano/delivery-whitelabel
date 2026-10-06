import re
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from .registry import RESOURCES


def react_url(url):
    from urllib.parse import urlsplit

    path = urlsplit(url).path
    special = {
        "/admin/": "/painel/",
        "/dashboard/": "/painel/",
        "/admin/login/": "/painel/login",
        "/admin/logout/": "/painel/logout",
        "/admin/password_change/": "/painel/senha",
        "/admin/password_change/done/": "/painel/",
        "/admin/atendimento-whatsapp/": "/painel/whatsapp",
        "/admin/minha-assinatura/": "/painel/assinatura",
        "/admin/notas-fiscais/": "/painel/notas",
        "/admin/taxas-pagamentos-online/": "/painel/taxas",
    }
    if path in special:
        return special[path]
    m = re.fullmatch(r"/admin/minha-assinatura/cobranca/([0-9a-f-]+)/", path)
    if m:
        return "/painel/cobrancas/" + m[1]
    for key, (label, _, _) in RESOURCES.items():
        prefix = "/admin/" + label.replace(".", "/") + "/"
        if path == prefix:
            return "/painel/" + key
        if path == prefix + "add/":
            return "/painel/" + key + "/novo"
        if path.startswith(prefix):
            bits = path[len(prefix) :].strip("/").split("/")
            if len(bits) >= 2 and bits[1] in ("change", "delete", "history"):
                return "/painel/" + key + "/" + bits[0]
    return "/painel/"


class MerchantCutoverMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "MERCHANT_REACT_ENABLED", False) and (
            request.path.startswith("/admin/")
            or request.path in ("/dashboard/", "/dashboard/login/")
        ):
            if request.method in ("GET", "HEAD"):
                return redirect(react_url(request.path))
            return JsonResponse(
                {"detail": "O painel foi atualizado. Acesse /painel/ para continuar."},
                status=409,
            )
        return self.get_response(request)
