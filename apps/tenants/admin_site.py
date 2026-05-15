from unfold.sites import UnfoldAdminSite


# ── Admin do Lojista ──────────────────────────────────────────────────────────
class TenantAdminSite(UnfoldAdminSite):
    site_title = "Painel"
    site_header = "Painel Admin"
    index_title = "Bem-vindo"
    settings_name = "UNFOLD"  # usa o UNFOLD do settings.py (com o sidebar do lojista)

    def each_context(self, request):
        ctx = super().each_context(request)
        tenant = getattr(request, 'tenant', None)
        if tenant and hasattr(tenant, 'brand_config'):
            brand = tenant.brand_config
            ctx['tenant_brand'] = brand
            ctx['site_header'] = tenant.name
            ctx['site_title'] = f"{tenant.name} - Painel"
        return ctx

    def has_permission(self, request):
        user = request.user
        if not user.is_active or not user.is_staff:
            return False
        if user.is_superuser:
            return True
        return getattr(request, 'tenant', None) and user.tenant_id == request.tenant.id


tenant_admin_site = TenantAdminSite(name='tenant_admin')


# ── Admin Global (Superusuário) ───────────────────────────────────────────────
class SuperAdminSite(UnfoldAdminSite):
    site_title = "Super Admin"
    site_header = "Painel Global"
    index_title = "Gestão do Sistema"
    settings_name = "UNFOLD_SUPER"  # usa uma config separada no settings.py

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser


super_admin_site = SuperAdminSite(name='super_admin')