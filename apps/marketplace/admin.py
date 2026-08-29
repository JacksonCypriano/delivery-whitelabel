from django import forms
from django.core.exceptions import ValidationError
from unfold.admin import ModelAdmin

from apps.tenants.admin_site import super_admin_site, tenant_admin_site
from apps.tenants.onboarding import get_store_setup

from .models import MarketplaceCategory, MarketplaceProfile


class MarketplaceCategoryAdmin(ModelAdmin):
    list_display = ("name", "slug", "is_active", "order")
    list_editable = ("is_active", "order")
    search_fields = ("name", "slug")
    ordering = ("order", "name")
    prepopulated_fields = {"slug": ("name",)}


class MarketplaceProfileTenantForm(forms.ModelForm):
    class Meta:
        model = MarketplaceProfile
        fields = "__all__"

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        if not self.instance.pk and "is_listed" in self.fields:
            self.fields["is_listed"].initial = False

    def clean(self):
        cleaned = super().clean()
        tenant = getattr(self.request, "tenant", None) or getattr(self.instance, "tenant", None)
        if cleaned.get("is_listed") and tenant:
            setup = get_store_setup(tenant, marketplace_data=cleaned)
            if not setup["complete"]:
                missing = ", ".join(step["title"] for step in setup["steps"] if step.get("required", True) and not step["complete"])
                raise ValidationError(
                    f"A loja ainda não pode ser publicada. Conclua primeiro: {missing}."
                )
        return cleaned


class MarketplaceProfileTenantAdmin(ModelAdmin):
    form = MarketplaceProfileTenantForm
    readonly_fields = ("tenant", "created_at", "updated_at")
    filter_horizontal = ("categories",)

    fieldsets = (
        (
            "Publicação no VemDeDelivery",
            {
                "fields": ("tenant", "is_listed"),
                "description": "A loja só poderá ser publicada quando todo o checklist obrigatório do painel estiver concluído.",
            },
        ),
        (
            "Informações públicas",
            {
                "fields": ("short_description", "search_keywords", "categories"),
                "description": "Essas informações ajudam o cliente a encontrar e entender sua loja.",
            },
        ),
        (
            "Localização para descoberta",
            {
                "fields": ("city", "state", "neighborhood", "latitude", "longitude", "service_radius_km"),
                "description": "Cidade, UF e bairro são obrigatórios. Latitude, longitude e raio são opcionais.",
            },
        ),
        (
            "Informações do sistema",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)

        class RequestBoundForm(form_class):
            def __init__(self, *args, **form_kwargs):
                form_kwargs["request"] = request
                super().__init__(*args, **form_kwargs)

        return RequestBoundForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tenant = getattr(request, "tenant", None)
        return qs.filter(tenant=tenant) if tenant else qs.none()

    def has_module_permission(self, request):
        return bool(getattr(request, "tenant", None))

    def has_view_permission(self, request, obj=None):
        tenant = getattr(request, "tenant", None)
        if not tenant:
            return False
        return obj is None or obj.tenant_id == tenant.id

    def has_change_permission(self, request, obj=None):
        tenant = getattr(request, "tenant", None)
        if not tenant:
            return False
        return obj is None or obj.tenant_id == tenant.id

    def has_add_permission(self, request):
        tenant = getattr(request, "tenant", None)
        return bool(tenant and not MarketplaceProfile.objects.filter(tenant=tenant).exists())

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not obj.tenant_id:
            obj.tenant = request.tenant
        super().save_model(request, obj, form, change)


super_admin_site.register(MarketplaceCategory, MarketplaceCategoryAdmin)
tenant_admin_site.register(MarketplaceProfile, MarketplaceProfileTenantAdmin)
