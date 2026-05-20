from unfold.admin import ModelAdmin

from .admin_site import tenant_admin_site, super_admin_site
from .models import BrandConfig, Tenant


# ── Admin Global (só Tenant) ──────────────────────────────────────────────────
class TenantAdmin(ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


super_admin_site.register(Tenant, TenantAdmin)


# ── Admin do Lojista (BrandConfig) ───────────────────────────────────────────
class TenantBrandConfigAdmin(ModelAdmin):
    list_display = ("tenant", "primary_color", "secondary_color")
    readonly_fields = ("tenant",)

    fieldsets = (
        ("Cores", {"fields": ("primary_color", "secondary_color")}),
        ("Mídia", {"fields": ("logo",)}),
        ("Domínio", {"fields": ("custom_domain",)}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        tenant = getattr(request, "tenant", None)

        if not tenant:
            return qs.none()

        return qs.filter(tenant=tenant)
    
    def has_module_permission(self, request):
        return True

    def has_view_permission(self, request, obj=None):
        return True


tenant_admin_site.register(BrandConfig, TenantBrandConfigAdmin)
