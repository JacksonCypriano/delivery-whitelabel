from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import ValidationError
from django.db.models import Q
from unfold.admin import ModelAdmin
from unfold.forms import UserChangeForm

from apps.tenants.admin_site import super_admin_site, tenant_admin_site
from apps.tenants.models import Tenant

from .merchant_onboarding import generate_temporary_password, schedule_merchant_welcome_email
from .models import User


class MerchantUserCreationForm(forms.ModelForm):
    """Criação de lojista sem senha digitada pelo gestor global."""

    # Declarado explicitamente para que o campo seja obrigatório já em
    # ``base_fields`` (e não apenas após a instanciação do formulário).
    # O e-mail é indispensável porque é o canal usado para entregar o
    # acesso inicial do lojista.
    email = forms.EmailField(required=True, label="E-mail")
    tenant = forms.ModelChoiceField(queryset=Tenant.objects.all(), required=True, label="Loja")

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "tenant")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Login"
        self.fields["username"].help_text = "Login que será enviado ao lojista por e-mail. Preferencialmente use o mesmo e-mail de acesso."
        self.fields["username"].widget.attrs.update({"placeholder": "Ex.: lojista@minhaloja.com.br", "autocomplete": "username"})
        self.fields["first_name"].widget.attrs.setdefault("placeholder", "Ex.: João")
        self.fields["last_name"].widget.attrs.setdefault("placeholder", "Ex.: da Silva")
        self.fields["email"].required = True
        self.fields["email"].help_text = "E-mail que receberá a senha temporária e os links da loja e do painel."
        self.fields["email"].widget.attrs.update({"placeholder": "Ex.: lojista@minhaloja.com.br", "autocomplete": "email"})
        self.fields["tenant"].required = True
        self.fields["tenant"].label = "Loja"
        self.fields["tenant"].help_text = "Selecione a loja à qual este acesso administrativo pertence."

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if User.objects.filter(email__iexact=username).exists():
            raise ValidationError("Este login já está sendo usado como e-mail de outra conta.")
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            raise ValidationError("Já existe uma conta cadastrada com este e-mail.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        # Marca explicitamente que o password ainda será provisionado pelo admin.
        user.set_unusable_password()
        user._provision_initial_access = True
        if commit:
            user.save()
        return user


# ── Admin Global (Superusuário) ───────────────────────────────────────────────
class CustomUserAdmin(ModelAdmin, BaseUserAdmin):
    form = UserChangeForm
    add_form = MerchantUserCreationForm

    list_display = ("username", "email", "tenant", "access_type", "initial_access_status", "is_active")
    list_filter = ("is_active", "tenant")
    search_fields = ("username", "first_name", "last_name", "email", "tenant__name")
    ordering = ("username",)

    fieldsets = (
        ("Usuário", {"fields": ("username", "password")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name", "email")}),
        ("Acesso", {"fields": ("tenant", "is_active", "must_change_password", "welcome_email_sent_at")}),
        ("Datas", {"fields": ("last_login", "date_joined"), "classes": ("collapse",)}),
    )

    add_fieldsets = (
        (
            "Acesso inicial do lojista",
            {
                "classes": ("wide",),
                "fields": ("username", "first_name", "last_name", "email", "tenant"),
                "description": (
                    "A senha temporária será gerada automaticamente e enviada ao e-mail informado. "
                    "No primeiro acesso, o lojista será obrigado a criar uma nova senha."
                ),
            },
        ),
    )

    readonly_fields = ("last_login", "date_joined", "must_change_password", "welcome_email_sent_at")

    actions = ("resend_initial_access",)

    @admin.display(description="Tipo de acesso", ordering="is_superuser")
    def access_type(self, obj):
        if obj.is_superuser:
            return "Gestor global"
        if obj.tenant_id:
            return "Administrador da loja"
        return "Cliente"

    @admin.display(description="Primeiro acesso")
    def initial_access_status(self, obj):
        if not obj.tenant_id:
            return "—"
        if obj.must_change_password and not obj.welcome_email_sent_at:
            return "E-mail pendente — reenviar acesso"
        if obj.must_change_password:
            return "Aguardando troca de senha"
        if obj.welcome_email_sent_at:
            return "Concluído"
        return "Conta existente"

    @admin.action(description="Gerar novo acesso inicial e reenviar boas-vindas")
    def resend_initial_access(self, request, queryset):
        from django.contrib.auth.hashers import make_password
        from django.db import transaction

        sent = 0
        skipped = 0
        for user in queryset.select_related("tenant"):
            if user.is_superuser or not user.tenant_id or not user.email:
                skipped += 1
                continue

            temporary_password = generate_temporary_password()
            with transaction.atomic():
                User.objects.filter(pk=user.pk).update(
                    password=make_password(temporary_password),
                    is_staff=True,
                    is_tenant_admin=True,
                    must_change_password=True,
                    welcome_email_sent_at=None,
                )
                schedule_merchant_welcome_email(user.pk, temporary_password)
            sent += 1

        if sent:
            self.message_user(
                request,
                f"Novo acesso inicial gerado para {sent} lojista(s). O e-mail de boas-vindas será enviado após a gravação.",
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"{skipped} conta(s) foram ignoradas por não serem lojistas com e-mail válido.",
                level=messages.WARNING,
            )

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

        temporary_password = None
        if (
            not change
            and obj.tenant_id
            and getattr(obj, "_provision_initial_access", False)
        ):
            temporary_password = generate_temporary_password()
            obj.set_password(temporary_password)
            obj.must_change_password = True
            obj.welcome_email_sent_at = None

        super().save_model(request, obj, form, change)

        if temporary_password:
            schedule_merchant_welcome_email(obj.pk, temporary_password)


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


from .models import SecurityEvent


@admin.register(SecurityEvent, site=super_admin_site)
class SecurityEventAdmin(ModelAdmin):
    list_display = ("created_at", "event", "scope", "user", "actor", "channel", "reason", "ip_address")
    list_filter = ("event", "scope", "channel", "reason", "created_at")
    search_fields = ("user__username", "user__email", "actor__username", "request_id", "identifier_hash")
    readonly_fields = tuple(field.name for field in SecurityEvent._meta.fields)
    ordering = ("-created_at", "-pk")
    date_hierarchy = "created_at"
    list_select_related = ("user", "actor")
    list_per_page = 50
    actions = None

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset if self.has_module_permission(request) else queryset.none()
