from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from unfold.forms import UserChangeForm, UserCreationForm

from apps.tenants.admin_site import super_admin_site, tenant_admin_site

from .models import User


# ── Admin Global (Superusuário) ───────────────────────────────────────────────
class CustomUserAdmin(ModelAdmin, BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    list_display = ("username", "email", "tenant", "is_tenant_admin", "is_staff")
    list_filter = ("is_tenant_admin", "is_staff", "tenant")

    fieldsets = BaseUserAdmin.fieldsets + (
        ("Informações de Tenant (Lojista)", {
            "fields": ("tenant", "is_tenant_admin"),
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Informações de Tenant (Lojista)", {
            "fields": ("tenant", "is_tenant_admin"),
        }),
    )

super_admin_site.register(User, CustomUserAdmin)


# ── Admin do Lojista ──────────────────────────────────────────────────────────
class TenantUserAdmin(ModelAdmin, BaseUserAdmin):
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Informações Pessoais", {"fields": ("first_name", "last_name", "email")}),
        ("Permissões", {"fields": ("is_active", "is_staff")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "password1", "password2", "email", "is_active", "is_staff"),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(tenant=request.tenant)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.tenant = request.tenant
        super().save_model(request, obj, form, change)
