from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from unfold.forms import UserChangeForm, UserCreationForm

from apps.tenants.admin_site import super_admin_site, tenant_admin_site

from .models import User


# ── Admin Global (Superusuário) ───────────────────────────────────────────────
class CustomUserAdmin(ModelAdmin, BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    list_display = ("username", "email", "tenant", "access_type", "is_active")
    list_filter = ("is_active", "tenant")
    search_fields = ("username", "first_name", "last_name", "email", "tenant__name")
    ordering = ("username",)

    fieldsets = (
        ("Usuário", {"fields": ("username", "password")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name", "email")}),
        ("Acesso", {"fields": ("tenant", "is_active")}),
        ("Datas", {"fields": ("last_login", "date_joined"), "classes": ("collapse",)}),
    )

    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "password1", "password2")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name", "email")}),
        ("Acesso", {"fields": ("tenant", "is_active")}),
    )

    readonly_fields = ("last_login", "date_joined")

    @admin.display(description="Tipo de acesso", ordering="is_superuser")
    def access_type(self, obj):
        if obj.is_superuser:
            return "Gestor global"
        if obj.tenant_id:
            return "Administrador da loja"
        return "Cliente"

    def save_model(self, request, obj, form, change):
        if obj.is_superuser:
            obj.tenant = None
            obj.is_tenant_admin = False
            obj.is_staff = True
        elif obj.tenant_id:
            obj.is_tenant_admin = True
            obj.is_staff = True
        else:
            obj.is_tenant_admin = False
            obj.is_staff = False

        super().save_model(request, obj, form, change)


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
