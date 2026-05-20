from unfold.sites import UnfoldAdminSite
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


from django.db import connection

logger.warning(f"DATABASE SETTINGS: {connection.settings_dict}")

# ── Admin do Lojista ──────────────────────────────────────────────────────────
class TenantAdminSite(UnfoldAdminSite):
    site_title = "Painel"
    site_header = "Painel Admin"
    index_title = "Bem-vindo"
    settings_name = "UNFOLD"

    def each_context(self, request):
        ctx = super().each_context(request)

        tenant = getattr(request, "tenant", None)

        if tenant and hasattr(tenant, "brand_config"):
            ctx.update({
                "tenant_brand": tenant.brand_config,
                "site_header": tenant.name,
                "site_title": f"{tenant.name} - Painel",
            })

        return ctx

    def has_permission(self, request):
        user = request.user
        tenant = getattr(request, "tenant", None)

        if not user.is_authenticated:
            return False

        if not user.is_active or not user.is_staff:
            return False

        # 🔴 bloqueia superuser no tenant admin
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