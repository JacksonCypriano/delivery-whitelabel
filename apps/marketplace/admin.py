from django import forms
from django.contrib import admin
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
        exclude = (
            "city",
            "state",
            "neighborhood",
            "latitude",
            "longitude",
            "service_radius_km",
        )

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        if not self.instance.pk and "is_listed" in self.fields:
            self.fields["is_listed"].initial = False

        if "short_description" in self.fields:
            self.fields["short_description"].widget.attrs.setdefault(
                "placeholder",
                "Ex.: Pizzas artesanais, porções e bebidas.",
            )
        if "search_keywords" in self.fields:
            self.fields["search_keywords"].widget.attrs.setdefault(
                "placeholder",
                "Ex.: pizza, artesanal, porções, bebidas",
            )

    def clean(self):
        cleaned = super().clean()
        tenant = getattr(self.request, "tenant", None) or getattr(self.instance, "tenant", None)
        if cleaned.get("is_listed") and tenant:
            setup = get_store_setup(tenant, marketplace_data=cleaned)
            if not setup["complete"]:
                missing = ", ".join(
                    step["title"]
                    for step in setup["steps"]
                    if step.get("required", True) and not step["complete"]
                )
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


class MarketingLeadAdmin(ModelAdmin):
    list_display = ("reference", "created_at", "utm_source", "utm_campaign", "contact_status", "tenant", "first_paid_status")
    search_fields = ("reference", "utm_source", "utm_campaign", "tenant__name", "tenant__slug")
    list_filter = ("analytics_consent", "source_note", "qualified_at", "linked_at")
    readonly_fields = (
        "reference", "tenant", "landing_path", "cta", "source_note", "analytics_consent", "ga_client_id",
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "gbraid", "wbraid",
        "linked_at", "created_at",
    )
    fields = readonly_fields + ("qualified_at",)
    actions = ("mark_qualified",)

    @staticmethod
    def contact_status(obj):
        return "Qualificado" if obj.qualified_at else "Clique no contato (não confirmado)"
    contact_status.short_description = "Situação"

    @staticmethod
    def first_paid_status(obj):
        from .models import MarketingPaidConversion
        conv = MarketingPaidConversion.objects.filter(lead=obj).first()
        return "Em revisão" if conv and conv.retracted_at else ("Pago" if conv else "Não confirmado")
    first_paid_status.short_description = "1ª assinatura"

    @admin.action(description="Marcar contato confirmado/qualificado")
    def mark_qualified(self, request, queryset):
        from django.utils import timezone
        from .acquisition import mark_qualified
        for lead in queryset:
            mark_qualified(lead)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.qualified_at:
            from .acquisition import mark_qualified
            mark_qualified(obj)

    def has_add_permission(self, request):
        return False  # Usar referência recebida no Superadmin ao criar loja.

    def has_delete_permission(self, request, obj=None):
        return False


class MarketingPaidConversionAdmin(ModelAdmin):
    list_display = ("lead", "invoice", "amount", "paid_at", "ga4_sent_at")
    list_filter = ("ga4_sent_at",)
    search_fields = ("lead__reference", "lead__tenant__name", "invoice__provider_id")
    readonly_fields = ("lead", "invoice", "amount", "paid_at", "retracted_at", "created_at", "ga4_sent_at", "ga4_last_error")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from .models import MarketingLead, MarketingPaidConversion  # noqa: E402
super_admin_site.register(MarketingLead, MarketingLeadAdmin)
super_admin_site.register(MarketingPaidConversion, MarketingPaidConversionAdmin)


class MarketingMilestoneAdmin(ModelAdmin):
    list_display = ("lead", "name", "occurred_at", "ga4_sent_at")
    search_fields = ("lead__reference", "lead__tenant__name")
    readonly_fields = ("lead", "name", "invoice", "occurred_at", "ga4_sent_at", "ga4_last_error")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from .models import MarketingMilestone  # noqa: E402
super_admin_site.register(MarketingMilestone, MarketingMilestoneAdmin)
