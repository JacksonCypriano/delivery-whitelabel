import pprint
import logging

from django.core.exceptions import ValidationError

from apps.tenants.models import BrandConfig
from apps.tenants.onboarding import get_store_setup
from .admin_security import (ProtectedAdminAuthenticationForm, ProtectedAdminSiteMixin, SuperAdminAuthenticationForm)
from unfold.sites import UnfoldAdminSite

logger = logging.getLogger(__name__)

class TenantAdminAuthenticationForm(ProtectedAdminAuthenticationForm):
    login_scope = "tenant"

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)

        tenant = getattr(self.request, "tenant", None)

        if (
            user.is_superuser
            or not getattr(user, "is_tenant_admin", False)
            or not getattr(user, "tenant_id", None)
            or not tenant
            or user.tenant_id != tenant.id
        ):
            from apps.accounts.audit import record_event
            record_event("access_denied", request=self.request, user_id=user.pk, reason="not_allowed")
            raise ValidationError(
                "Credenciais inválidas para esta loja.",
                code="invalid_tenant_login",
            )


# ── Admin do Lojista ──────────────────────────────────────────────────────────
class TenantAdminSite(ProtectedAdminSiteMixin, UnfoldAdminSite):
    login_form = TenantAdminAuthenticationForm
    site_title = "Painel"
    site_header = "Painel da loja"
    index_title = "Bem-vindo"
    settings_name = "UNFOLD"

    def get_urls(self):
        from django.urls import path
        from apps.billing import views
        return [
            path('minha-assinatura/', self.admin_view(views.dashboard), name='billing_dashboard'),
            path('minha-assinatura/comprar/', self.admin_view(views.purchase), name='billing_purchase'),
            path('minha-assinatura/cobranca/<uuid:invoice_id>/', self.admin_view(views.invoice_detail), name='billing_invoice'),
            path('minha-assinatura/cobranca/<uuid:invoice_id>/consultar/', self.admin_view(views.refresh), name='billing_refresh'),
            path('minha-assinatura/cobranca/<uuid:invoice_id>/nota/<str:kind>/', self.admin_view(views.fiscal_download), name='billing_fiscal_download'),
        ] + super().get_urls()

    def _store_setup_app(self, tenant):
        setup = get_store_setup(tenant)
        status = "Pronta para publicar" if setup["complete"] else "Finalize a configuração da sua loja"

        models = [
            {
                "name": f"Progresso da configuração — {setup['percent']}% ({setup['completed']}/{setup['total']} concluídos)",
                "object_name": "StoreSetupProgress",
                "perms": {"add": False, "change": False, "delete": False, "view": True},
                "admin_url": "",
                "add_url": None,
                "view_only": True,
            }
        ]

        for index, step in enumerate(setup["steps"], start=1):
            if not step.get("required", True):
                continue

            step_status = "Concluído" if step["complete"] else "Pendente"
            models.append({
                "name": f"{step['title']} — {step_status}",
                "object_name": f"StoreSetupStep{index}",
                "perms": {"add": False, "change": True, "delete": False, "view": True},
                "admin_url": step.get("url") or "",
                "add_url": None,
                "view_only": False,
            })

        return {
            "name": f"{status} · {setup['percent']}%",
            "app_label": "store_setup",
            "app_url": "",
            "has_module_perms": True,
            "models": models,
        }

    def index(self, request, extra_context=None):
        tenant = getattr(request, "tenant", None)
        app_list = self.get_app_list(request)

        if tenant:
            app_list = [self._store_setup_app(tenant), *app_list]

        extra_context = {**(extra_context or {}), "app_list": app_list}
        return super().index(request, extra_context=extra_context)

    def each_context(self, request):
        ctx = super().each_context(request)

        tenant = getattr(request, "tenant", None)
        logo_url = "/static/images/logo.png"
        tenant_name = "Painel"

        if tenant:
            tenant_name = tenant.name

            ctx["site_header"] = tenant_name
            ctx["site_title"] = f"{tenant_name} - Painel"
            ctx["index_title"] = f"Bem-vindo ao painel de {tenant_name}"

            brand = BrandConfig.objects.filter(tenant=tenant).first()

            if brand and brand.logo:
                logo_url = brand.logo.url

            ctx["site_logo"] = logo_url
            ctx["site_symbol"] = "store"

            ctx["show_history"] = True
            ctx["show_view_on_site"] = False
            ctx["show_back_button"] = False

        else:
            ctx["site_header"] = "Administração global"
            ctx["site_title"] = "Painel Global"
            ctx["index_title"] = "Gestão do Sistema"

            ctx["site_logo"] = "/static/images/logo.png"
            ctx["site_symbol"] = "admin_panel_settings"

        if tenant and request.user.is_authenticated and self.has_permission(request):
            from apps.billing.services import get_subscription
            ctx['billing_subscription'] = get_subscription(tenant)
        return ctx

    def has_permission(self, request):
        user = request.user
        tenant = getattr(request, "tenant", None)

        if not user.is_authenticated:
            return False

        if not user.is_active or not user.is_staff or not user.is_tenant_admin:
            return False

        if user.is_superuser:
            return False

        if not tenant:
            return False

        if not getattr(user, "tenant_id", None):
            return False

        return user.tenant_id == tenant.id

tenant_admin_site = TenantAdminSite(name="tenant_admin")


# ── Admin Global (Superusuário) ───────────────────────────────────────────────
class SuperAdminSite(ProtectedAdminSiteMixin, UnfoldAdminSite):
    login_form = SuperAdminAuthenticationForm
    site_title = "Administração global"
    site_header = "Painel Global"
    index_title = "Gestão do Sistema"
    settings_name = "UNFOLD_SUPER"

    def has_permission(self, request):
        user = request.user

        return (
            user.is_authenticated and
            user.is_active and
            user.is_superuser
        )


super_admin_site = SuperAdminSite(name="super_admin")
