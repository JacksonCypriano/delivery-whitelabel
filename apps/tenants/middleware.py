from .models import Tenant
from .domains import tenant_slug_from_request
import logging

from django.shortcuts import redirect
from django.urls import reverse

from apps.core.observability import set_tenant_slug

logger = logging.getLogger(__name__)

class TenantMiddleware:
    """Resolve tenant exclusively from the host.

    The path never changes tenant scope. This is intentional: the platform
    panel lives at dominio/painel/ and a merchant panel at
    slug.dominio/painel/.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        subdomain = tenant_slug_from_request(request)
        tenant = None

        if subdomain:
            try:
                tenant = Tenant.objects.get(slug=subdomain)
            except Tenant.DoesNotExist:
                # Compatibilidade da vitrine demo: o domínio público foi renomeado
                # de vitrine-demo para demo sem exigir renomear o tenant existente.
                demo_alias = {"demo": "vitrine-demo", "vitrine-demo": "demo"}.get(subdomain)
                tenant = (
                    Tenant.objects.filter(slug=demo_alias).first()
                    if demo_alias
                    else None
                )

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
