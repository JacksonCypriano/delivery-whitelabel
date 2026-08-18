from django.contrib import admin
from unfold.admin import ModelAdmin

from .admin_site import super_admin_site, tenant_admin_site
from .models import BrandConfig, Tenant


# ── Admin Global (só Tenant) ──────────────────────────────────────────────────
class TenantAdmin(ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


super_admin_site.register(Tenant, TenantAdmin)


# ── Admin do Lojista: Configurações da Loja (Tenant) ─────────────────────────
class StoreSettingsAdmin(ModelAdmin):
    """Permite ao lojista editar as informações da própria loja (white-label):
    nome, WhatsApp, endereço, horário de funcionamento e taxa de entrega.
    """
    list_display = ("name", "whatsapp_number", "delivery_fee", "is_active")
    readonly_fields = ("slug", "sale_mode", "created_at")

    fieldsets = (
        ("Informações da loja", {
            "fields": ("name", "slug", "whatsapp_number"),
        }),
        ("Localização e atendimento", {
            "fields": ("address", "business_hours", "delivery_time_estimate"),
        }),
        ("Entrega", {
            "fields": ("delivery_fee",),
        }),
        ("Status", {
            "fields": ("sale_mode", "is_active", "created_at"),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tenant = getattr(request, "tenant", None)
        if not tenant:
            return qs.none()
        return qs.filter(pk=tenant.pk)

    # A loja é criada pelo super admin; o lojista apenas edita a própria.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return True

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


tenant_admin_site.register(Tenant, StoreSettingsAdmin)


# ── Admin do Lojista (BrandConfig) ───────────────────────────────────────────
class TenantBrandConfigAdmin(ModelAdmin):
    list_display = ("tenant", "primary_color", "secondary_color")
    readonly_fields = ("tenant",)

    fieldsets = (
        ("Cores", {"fields": ("primary_color", "secondary_color", "accent_color", "background_color", "text_color", "dark_mode_primary", "dark_mode_background", "dark_mode_text")}),
        ("Mídia", {"fields": ("logo", "favicon", "banner")}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        tenant = getattr(request, "tenant", None)

        if not tenant:
            return qs.none()

        return qs.filter(tenant=tenant)
    
    def save_model(self, request, obj, form, change):
        if not obj.tenant_id:
            obj.tenant = getattr(request, "tenant", None)
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        return True

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return True

    def has_delete_permission(self, request, obj=None):
        return True


tenant_admin_site.register(BrandConfig, TenantBrandConfigAdmin)
