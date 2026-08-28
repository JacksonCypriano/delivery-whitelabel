from apps.tenants.admin_site import super_admin_site, tenant_admin_site
from unfold.admin import ModelAdmin

from .models import MarketplaceCategory, MarketplaceProfile


class MarketplaceCategoryAdmin(ModelAdmin):
    list_display = ("name", "slug", "is_active", "order")
    list_editable = ("is_active", "order")
    search_fields = ("name", "slug")
    ordering = ("order", "name")
    prepopulated_fields = {"slug": ("name",)}


class MarketplaceProfileSuperAdmin(ModelAdmin):
    list_display = (
        "tenant",
        "city",
        "state",
        "is_listed",
        "is_featured",
        "priority",
    )
    list_filter = (
        "is_listed",
        "is_featured",
        "state",
        "city",
        "categories",
    )
    search_fields = (
        "tenant__name",
        "short_description",
        "search_keywords",
        "city",
        "neighborhood",
    )
    filter_horizontal = ("categories",)


class MarketplaceProfileTenantAdmin(ModelAdmin):
    readonly_fields = ("tenant", "is_featured", "priority", "created_at", "updated_at")
    filter_horizontal = ("categories",)

    fieldsets = (
        (
            "Exibição",
            {
                "fields": (
                    "tenant",
                    "is_listed",
                    "short_description",
                    "search_keywords",
                    "categories",
                ),
            },
        ),
        (
            "Localização para descoberta",
            {
                "fields": (
                    "city",
                    "state",
                    "neighborhood",
                    "latitude",
                    "longitude",
                    "service_radius_km",
                ),
            },
        ),
        (
            "Administração da plataforma",
            {
                "fields": (
                    "is_featured",
                    "priority",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tenant = getattr(request, "tenant", None)
        return qs.filter(tenant=tenant) if tenant else qs.none()

    def has_add_permission(self, request):
        tenant = getattr(request, "tenant", None)
        if not tenant:
            return False
        return not MarketplaceProfile.objects.filter(tenant=tenant).exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not obj.tenant_id:
            obj.tenant = request.tenant
        super().save_model(request, obj, form, change)


super_admin_site.register(MarketplaceCategory, MarketplaceCategoryAdmin)
super_admin_site.register(MarketplaceProfile, MarketplaceProfileSuperAdmin)
tenant_admin_site.register(MarketplaceProfile, MarketplaceProfileTenantAdmin)
