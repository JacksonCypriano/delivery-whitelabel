import pprint
import logging

from apps.tenants.models import BrandConfig
from unfold.sites import UnfoldAdminSite

logger = logging.getLogger(__name__)

# ── Admin do Lojista ──────────────────────────────────────────────────────────
class TenantAdminSite(UnfoldAdminSite):
    site_title = "Painel"
    site_header = "Painel Admin"
    index_title = "Bem-vindo"
    settings_name = "UNFOLD"

    def each_context(self, request):
        ctx = super().each_context(request)

        tenant = getattr(request, "tenant", None)
        logo_url = "/static/images/logo.png"
        tenant_name = "Painel"

        if tenant:
            tenant_name = tenant.name

            ctx["site_header"] = tenant_name
            ctx["site_title"] = f"{tenant_name} - Painel"
            ctx["index_title"] = f"Bem-vindo ao painel de {tenant_name}"

            brand = BrandConfig.objects.filter(tenant=tenant).first()

            if brand and brand.logo:
                logo_url = brand.logo.url

            ctx["site_logo"] = logo_url
            ctx["site_symbol"] = "store"

            ctx["show_history"] = True
            ctx["show_view_on_site"] = False
            ctx["show_back_button"] = False

        else:
            ctx["site_header"] = "Super Admin"
            ctx["site_title"] = "Painel Global"
            ctx["index_title"] = "Gestão do Sistema"

            ctx["site_logo"] = "/static/images/logo.png"
            ctx["site_symbol"] = "admin_panel_settings"

        return ctx

    def has_permission(self, request):
        user = request.user
        tenant = getattr(request, "tenant", None)

        if not user.is_authenticated:
            return False

        if not user.is_active or not user.is_staff:
            return False

        if user.is_superuser:
            return False

        if not tenant:
            return False

        if not getattr(user, "tenant_id", None):
            return False

        return user.tenant_id == tenant.id

tenant_admin_site = TenantAdminSite(name="tenant_admin")


# ── Admin Global (Superusuário) ───────────────────────────────────────────────
class SuperAdminSite(UnfoldAdminSite):
    site_title = "Super Admin"
    site_header = "Painel Global"
    index_title = "Gestão do Sistema"
    settings_name = "UNFOLD_SUPER"

    def has_permission(self, request):
        user = request.user

        return (
            user.is_authenticated and
            user.is_active and
            user.is_superuser
        )


super_admin_site = SuperAdminSite(name="super_admin")