import pprint
import logging

from django.core.exceptions import ValidationError
from django.contrib.auth.forms import PasswordChangeForm

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
    password_change_form = PasswordChangeForm
    site_title = "Painel"
    site_header = "Painel da loja"
    index_title = "Bem-vindo"
    settings_name = "UNFOLD"
    index_template = "admin/tenant/index.html"

    # Ordem pensada para o lojista configurar a operação antes de entrar
    # nos módulos de uso recorrente. O bloco de primeiros passos aparece
    # separadamente no topo do dashboard.
    _app_order = {
        "tenants": 10,
        "stores": 20,
        "marketplace": 30,
        "orders": 40,
        "customers": 50,
        "coupons": 60,
    }

    _app_display_names = {
        "tenants": "Gestão da Loja",
        "stores": "Cardápio",
        "marketplace": "Finalize e publique",
    }

    _model_order = {
        "tenants": {
            "Tenant": 10,
            "BrandConfig": 20,
            "BusinessHour": 30,
            "DeliveryZone": 40,
        },
        "marketplace": {"MarketplaceProfile": 10},
        "stores": {
            "Category": 10,
            "Product": 20,
            "CustomizationGroup": 30,
            "CustomizationGroupLabel": 40,
        },
        "orders": {"Order": 10},
        "customers": {"Customer": 10},
        "coupons": {
            "CouponCampaign": 10,
            "CouponRedemption": 20,
        },
    }

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)

        for app in app_list:
            app["name"] = self._app_display_names.get(app["app_label"], app["name"])
            model_order = self._model_order.get(app["app_label"], {})
            app["models"].sort(
                key=lambda model: (
                    model_order.get(model["object_name"], 9999),
                    str(model["name"]).casefold(),
                )
            )

        app_list.sort(
            key=lambda app: (
                self._app_order.get(app["app_label"], 9999),
                str(app["name"]).casefold(),
            )
        )
        return app_list

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

    def index(self, request, extra_context=None):
        tenant = getattr(request, "tenant", None)
        store_setup = get_store_setup(tenant) if tenant else None

        extra_context = {
            **(extra_context or {}),
            "store_setup": store_setup,
        }
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

            from apps.marketplace.services import build_tenant_url
            ctx["store_public_url"] = build_tenant_url(tenant)

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
    index_template = "admin/super/index.html"

    _app_order = {
        "tenants": 10,
        "accounts": 20,
        "billing": 30,
        "integrations": 40,
        "marketplace": 50,
    }

    _model_order = {
        "tenants": {"Tenant": 10},
        "accounts": {"User": 10, "SecurityEvent": 20},
        "billing": {
            "Subscription": 10,
            "Invoice": 20,
            "Credit": 30,
            "Plan": 40,
            "AdditionalService": 50,
            "TenantPaymentAccount": 60,
            "BillingSettings": 70,
            "BillingEvent": 80,
            "BillingAudit": 90,
            "FiscalInvoice": 100,
            "FiscalSettings": 110,
            "FiscalCustomerRule": 120,
            "TaxRate": 130,
            "MunicipalExport": 140,
        },
        "integrations": {
            "WhatsAppIntegrationState": 10,
            "WhatsAppIntegrationEvent": 20,
            "WhatsAppAlert": 30,
        },
        "marketplace": {"MarketplaceCategory": 10},
    }

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)

        for app in app_list:
            model_order = self._model_order.get(app["app_label"], {})
            app["models"].sort(
                key=lambda model: (
                    model_order.get(model["object_name"], 9999),
                    str(model["name"]).casefold(),
                )
            )

        app_list.sort(
            key=lambda app: (
                self._app_order.get(app["app_label"], 9999),
                str(app["name"]).casefold(),
            )
        )
        return app_list

    def has_permission(self, request):
        user = request.user

        return (
            user.is_authenticated and
            user.is_active and
            user.is_superuser
        )


super_admin_site = SuperAdminSite(name="super_admin")
