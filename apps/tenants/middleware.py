from .models import Tenant
import logging

from django.shortcuts import redirect
from django.urls import reverse

from apps.core.observability import set_tenant_slug

logger = logging.getLogger(__name__)

class TenantMiddleware:
    """Resolve o tenant atual a partir do subdomínio da requisição.

    Rotas iniciadas em /superadmin não pertencem a nenhum tenant (request.tenant = None).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/superadmin'):
            request.tenant = None
            set_tenant_slug('-')
            return self.get_response(request)

        host = request.META.get('HTTP_HOST', '')
        subdomain = host.split('.')[0]

        try:
            tenant = Tenant.objects.get(slug=subdomain)
        except Tenant.DoesNotExist:
            tenant = None

        request.tenant = tenant
        set_tenant_slug(getattr(tenant, "slug", "-") if tenant is not None else "-")
        logger.debug("Requisição para %s resolvida para tenant: %s", request.path, tenant)
        return self.get_response(request)


class ForceInitialPasswordChangeMiddleware:
    """Bloqueia o painel do lojista até a troca da senha temporária."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        tenant = getattr(request, "tenant", None)

        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "is_tenant_admin", False)
            and getattr(user, "must_change_password", False)
            and tenant is not None
            and getattr(user, "tenant_id", None) == tenant.pk
            and request.path.startswith("/admin/")
        ):
            password_change_url = reverse("tenant_admin:password_change")
            logout_url = reverse("tenant_admin:logout")
            if request.path not in {password_change_url, logout_url}:
                return redirect(password_change_url)

        return self.get_response(request)
