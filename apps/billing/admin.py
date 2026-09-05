from django.contrib import admin
from django.db import transaction
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils import timezone
from datetime import timedelta
from unfold.admin import ModelAdmin
from apps.tenants.admin_site import super_admin_site
from .models import (
    BillingSettings,
    Plan,
    AdditionalService,
    Subscription,
    Invoice,
    Credit,
    BillingAudit,
    BillingEvent,
    TenantPaymentAccount,
)
from .services import set_store, audit
from .online import request_subaccount
from .provider import BillingError


class GlobalAdmin(ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BillingSettings, site=super_admin_site)
class SettingsAdmin(GlobalAdmin):
    def has_add_permission(self, request):
        return (
            super().has_add_permission(request) and not BillingSettings.objects.exists()
        )


@admin.register(Plan, site=super_admin_site)
class PlanAdmin(GlobalAdmin):
    list_display = ["name", "months", "monthly_price", "discount", "plan_price", "active"]

    @admin.display(description="Valor do plano")
    def plan_price(self, obj):
        return obj.price


@admin.register(AdditionalService, site=super_admin_site)
class AdditionalServiceAdmin(GlobalAdmin):
    list_display = ["name", "code", "price", "active"]
    list_editable = ["price", "active"]
    search_fields = ["name", "code"]


class DueFilter(admin.SimpleListFilter):
    title = "Vencimento da assinatura"
    parameter_name = "vencimento"

    def lookups(self, request, model_admin):
        return [
            ("current", "Em dia"),
            ("soon", "Vence em até 7 dias"),
            ("overdue", "Vencida"),
        ]

    def queryset(self, request, queryset):
        today = timezone.localdate()
        if self.value() == "current":
            return queryset.filter(managed=True, valid_until__gt=today)
        if self.value() == "soon":
            return queryset.filter(
                managed=True,
                valid_until__gt=today,
                valid_until__lte=today + timedelta(days=7),
            )
        if self.value() == "overdue":
            return queryset.filter(managed=True, valid_until__lte=today)
        return queryset


@admin.register(Subscription, site=super_admin_site)
class SubscriptionAdmin(GlobalAdmin):
    list_display = [
        "tenant",
        "subscription_status",
        "valid_until",
        "managed",
        "billing_suspended",
        "manually_blocked",
        "payment_review",
        "credit_link",
    ]
    list_filter = [
        DueFilter,
        "managed",
        "billing_suspended",
        "manually_blocked",
        "payment_review",
    ]
    search_fields = ["tenant__name", "tenant__slug"]
    readonly_fields = ["tenant", "billing_suspended", "created_at", "credit_link"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="Situação")
    def subscription_status(self, obj):
        return obj.situation

    @admin.display(description="Registrar recebimento / cortesia")
    def credit_link(self, obj):
        return format_html(
            '<a href="{}">Acrescentar meses</a>',
            reverse("super_admin:billing_manual_credit", args=[obj.tenant_id]),
        )

    def get_urls(self):
        from .views import grant_manual

        return [
            path(
                "credit/<int:tenant_id>/",
                self.admin_site.admin_view(grant_manual),
                name="billing_manual_credit",
            )
        ] + super().get_urls()

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            before = Subscription.objects.select_for_update().get(pk=obj.pk)
            # Formulário aberto antes de um pagamento não pode sobrescrever o saldo novo.
            desired = {field: getattr(obj, field) for field in form.changed_data}
            changes = "; ".join(
                f"{field}: {getattr(before,field)} → {value}"
                for field, value in desired.items()
            )
            for field, value in desired.items():
                setattr(before, field, value)
            if "valid_until" in desired and before.valid_until:
                before.anchor_day = before.valid_until.day
            if not before.managed:
                before.billing_suspended = False
            if before.managed and before.valid_until:
                from django.utils import timezone

                if before.valid_until > timezone.localdate():
                    before.billing_suspended = False
            before.save()
            set_store(before)
            audit(before, "Ajuste administrativo", changes, request.user)
            for field in before._meta.concrete_fields:
                setattr(obj, field.attname, getattr(before, field.attname))


class ReadOnlyAdmin(GlobalAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]


@admin.register(Invoice, site=super_admin_site)
class InvoiceAdmin(ReadOnlyAdmin):
    list_display = [
        "tenant",
        "plan_name", "additional_service",
        "method",
        "amount",
        "status",
        "environment",
        "created_at",
        "paid_at",
    ]
    list_filter = ["status", "method", "environment"]
    search_fields = ["tenant__name", "tenant__slug", "provider_id"]


@admin.register(Credit, site=super_admin_site)
class CreditAdmin(ReadOnlyAdmin):
    list_display = [
        "tenant",
        "months",
        "previous_until",
        "valid_until",
        "reason",
        "actor",
        "created_at",
    ]
    search_fields = ["tenant__name", "reason"]


@admin.register(BillingAudit, site=super_admin_site)
class AuditAdmin(ReadOnlyAdmin):
    list_display = ["tenant", "action", "detail", "actor", "created_at"]
    search_fields = ["tenant__name", "action"]


@admin.register(BillingEvent, site=super_admin_site)
class EventAdmin(ReadOnlyAdmin):
    list_display = [
        "event_id",
        "event_kind",
        "environment",
        "processed_at",
        "attempts",
        "created_at",
    ]

    @admin.display(description="Tipo da notificação", ordering="kind")
    def event_kind(self, obj):
        labels = {
            "PAYMENT_CREATED": "Cobrança criada",
            "PAYMENT_UPDATED": "Cobrança atualizada",
            "PAYMENT_CONFIRMED": "Pagamento confirmado",
            "PAYMENT_RECEIVED": "Pagamento recebido",
            "PAYMENT_OVERDUE": "Cobrança vencida",
            "PAYMENT_DELETED": "Cobrança excluída",
            "PAYMENT_RESTORED": "Cobrança restaurada",
            "PAYMENT_REFUNDED": "Pagamento estornado",
            "PAYMENT_PARTIALLY_REFUNDED": "Pagamento parcialmente estornado",
            "PAYMENT_REFUND_IN_PROGRESS": "Estorno em processamento",
            "PAYMENT_REFUND_DENIED": "Estorno recusado",
            "PAYMENT_CHARGEBACK_REQUESTED": "Contestação solicitada",
            "PAYMENT_CHARGEBACK_DISPUTE": "Contestação em análise",
            "PAYMENT_AWAITING_CHARGEBACK_REVERSAL": "Aguardando reversão da contestação",
            "CHECKOUT_PAID": "Checkout pago",
            "CHECKOUT_EXPIRED": "Checkout expirado",
            "CHECKOUT_CANCELED": "Checkout cancelado",
            "PAYMENT_DUNNING_REQUESTED": "Negativação solicitada",
            "PAYMENT_DUNNING_RECEIVED": "Negativação recebida",
        }
        return labels.get(obj.kind, "Notificação de cobrança")


@admin.register(TenantPaymentAccount, site=super_admin_site)
class TenantPaymentAccountAdmin(GlobalAdmin):
    list_display = ["tenant", "status", "enabled", "provider_account_id", "updated_at"]
    list_filter = ["status", "enabled"]
    search_fields = ["tenant__name", "tenant__slug", "document", "provider_account_id"]
    readonly_fields = ["provider_account_id", "wallet_id", "encrypted_api_key", "activation_url", "requested_at", "approved_at", "last_error", "terms_accepted_at", "created_at", "updated_at"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.enabled and not obj.provider_account_id:
            try:
                request_subaccount(obj)
                self.message_user(request, "Subconta solicitada ao Asaas; aguarde a aprovação cadastral.")
            except BillingError as exc:
                self.message_user(request, str(exc), level="ERROR")


from . import fiscal_admin  # noqa: E402,F401
