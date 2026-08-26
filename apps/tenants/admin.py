from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.admin import TabularInline

from .admin_site import super_admin_site, tenant_admin_site
from .models import BrandConfig, Tenant, DeliveryZone, BusinessHour


# ── Admin Global (só Tenant) ──────────────────────────────────────────────────
class TenantAdmin(ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


super_admin_site.register(Tenant, TenantAdmin)


class DeliveryZoneInline(TabularInline):
    model = DeliveryZone
    extra = 1
    fields = ('city', 'neighborhood', 'fee', 'is_active')


class BusinessHourInline(TabularInline):
    model = BusinessHour

    fields = (
        "weekday",
        "is_closed",
        "opening_time",
        "closing_time",
    )

    ordering = (
        "weekday",
        "opening_time",
    )

    extra = 1

    can_delete = True

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return True


# ── Admin do Lojista: Configurações da Loja (Tenant) ─────────────────────────
class StoreSettingsAdmin(ModelAdmin):
    """
    Permite ao lojista editar as informações da própria loja.
    """

    list_display = (
        "name",
        "whatsapp_number",
        "is_active",
    )

    readonly_fields = (
        "slug",
        "sale_mode",
        "created_at",
    )

    fieldsets = (
        (
            "Informações da loja",
            {
                "fields": (
                    "name",
                    "slug",
                    "whatsapp_number",
                    "fulfillment_mode",
                ),
            },
        ),
        (
            "Endereço para retirada",
            {
                "fields": (
                    "pickup_address",
                    "pickup_number",
                    "pickup_complement",
                    "pickup_neighborhood",
                    "pickup_city",
                    "pickup_zip_code",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "sale_mode",
                    "is_active",
                    "created_at",
                ),
            },
        ),
    )

    def get_inlines(self, request, obj=None):
        inlines = [BusinessHourInline]

        if obj is None or obj.accepts_delivery:
            inlines.append(DeliveryZoneInline)

        return inlines

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        tenant = getattr(request, "tenant", None)

        if not tenant:
            return qs.none()

        return qs.filter(pk=tenant.pk)

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

@admin.register(DeliveryZone, site=tenant_admin_site)
class DeliveryZoneAdmin(ModelAdmin):
    list_display = ("city", "neighborhood", "fee", "is_active")
    list_editable = ("is_active",)
    list_filter = ("city", "is_active")
    search_fields = ("city", "neighborhood")

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        tenant = getattr(request, "tenant", None)

        if not tenant or not tenant.accepts_delivery:
            return qs.none()

        return qs.filter(tenant=tenant)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.tenant = request.tenant

        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        tenant = getattr(request, "tenant", None)
        return bool(tenant and tenant.accepts_delivery)


    def has_view_permission(self, request, obj=None):
        tenant = getattr(request, "tenant", None)
        return bool(tenant and tenant.accepts_delivery)


    def has_add_permission(self, request):
        tenant = getattr(request, "tenant", None)
        return bool(tenant and tenant.accepts_delivery)


    def has_change_permission(self, request, obj=None):
        tenant = getattr(request, "tenant", None)
        return bool(tenant and tenant.accepts_delivery)


    def has_delete_permission(self, request, obj=None):
        tenant = getattr(request, "tenant", None)
        return bool(tenant and tenant.accepts_delivery)


@admin.register(BusinessHour, site=tenant_admin_site)
class BusinessHourAdmin(ModelAdmin):
    list_display = (
        "tenant",
        "weekday",
        "is_closed",
        "opening_time",
        "closing_time",
    )

    list_filter = (
        "tenant",
        "weekday",
        "is_closed",
    )

    ordering = (
        "tenant",
        "weekday",
    )

    readonly_fields = (
        "tenant",
        "weekday",
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

    def has_change_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False