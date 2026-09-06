from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.html import format_html

from apps.core.admin import TenantModelAdmin, TenantInlineMixin, TenantPermissionMixin, tenant_admin_allowed
from apps.tenants.admin_site import tenant_admin_site
from unfold.admin import TabularInline, ModelAdmin

from .models import (
    AudienceType,
    CouponAssignment,
    CouponCampaign,
    CouponRedemption,
    DiscountType,
)




class CouponCampaignAdminForm(forms.ModelForm):
    class Meta:
        model = CouponCampaign
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "code" in self.fields:
            self.fields["code"].help_text = "Código que o cliente digita. Ex.: BEMVINDO10. O sistema salva em maiúsculas."
            self.fields["code"].widget.attrs.update({"placeholder": "Ex.: BEMVINDO10", "autocomplete": "off"})
        if "discount_type" in self.fields:
            self.fields["discount_type"].help_text = "Escolha entre percentual, valor fixo ou frete grátis."
        if "discount_value" in self.fields:
            self.fields["discount_value"].localize = True
            self.fields["discount_value"].widget.is_localized = True
            self.fields["discount_value"].help_text = (
                "Percentual: 10 significa 10%. Valor fixo: 10,00 significa R$ 10,00. "
                "Para frete grátis, deixe 0,00."
            )
            self.fields["discount_value"].widget.attrs.update({"placeholder": "Ex.: 10,00", "inputmode": "decimal"})
        if "minimum_order_value" in self.fields:
            self.fields["minimum_order_value"].localize = True
            self.fields["minimum_order_value"].widget.is_localized = True
            self.fields["minimum_order_value"].help_text = "Valor mínimo do carrinho para o cupom funcionar. Use 0,00 para não exigir mínimo."
            self.fields["minimum_order_value"].widget.attrs.update({"placeholder": "Ex.: 50,00", "inputmode": "decimal"})
        if "inactive_days" in self.fields:
            self.fields["inactive_days"].help_text = "Usado somente para público 'Clientes inativos'. Ex.: 30 dias."
            self.fields["inactive_days"].widget.attrs.update({"placeholder": "Ex.: 30", "inputmode": "numeric"})
        if "minimum_orders" in self.fields:
            self.fields["minimum_orders"].help_text = "Usado para público 'Clientes frequentes'. Ex.: 5 pedidos."
            self.fields["minimum_orders"].widget.attrs.update({"placeholder": "Ex.: 5", "inputmode": "numeric"})
        if "minimum_spent" in self.fields:
            self.fields["minimum_spent"].localize = True
            self.fields["minimum_spent"].widget.is_localized = True
            self.fields["minimum_spent"].help_text = "Opcional. Valor total já gasto pelo cliente. Ex.: 200,00."
            self.fields["minimum_spent"].widget.attrs.update({"placeholder": "Ex.: 200,00", "inputmode": "decimal"})
        if "usage_limit" in self.fields:
            self.fields["usage_limit"].help_text = "Opcional. Quantidade máxima de usos do cupom no total. Vazio = sem limite global."
            self.fields["usage_limit"].widget.attrs.update({"placeholder": "Ex.: 100", "inputmode": "numeric"})
        if "usage_limit_per_customer" in self.fields:
            self.fields["usage_limit_per_customer"].help_text = "Quantidade máxima que cada cliente pode usar este cupom. Ex.: 1."
            self.fields["usage_limit_per_customer"].widget.attrs.update({"placeholder": "Ex.: 1", "inputmode": "numeric"})


class CouponAssignmentInline(TenantInlineMixin, TabularInline):
    tenant_lookup = "campaign__tenant"
    model = CouponAssignment

    extra = 0

    fields = (
        "customer",
        "assigned_at",
    )

    readonly_fields = (
        "assigned_at",
    )

    autocomplete_fields = (
        "customer",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.select_related(
            "customer",
            "customer__user",
        )


class CouponCampaignAdmin(TenantModelAdmin):
    form = CouponCampaignAdminForm
    list_display = (
        "code_display",
        "name",
        "discount_display",
        "audience_display",
        "period_display",
        "usage_display",
        "status_badge",
    )

    list_filter = (
        "is_active",
        "discount_type",
        "audience_type",
        "starts_at",
        "ends_at",
    )

    search_fields = (
        "name",
        "code",
    )

    ordering = (
        "-created_at",
    )

    date_hierarchy = "created_at"

    list_per_page = 25

    readonly_fields = (
        "created_at",
        "updated_at",
        "total_redemptions",
        "total_discount_given",
    )

    fieldsets = (
        (
            "Campanha",
            {
                "fields": (
                    "name",
                    "code",
                    "is_active",
                ),
            },
        ),
        (
            "Desconto",
            {
                "fields": (
                    "discount_type",
                    "discount_value",
                    "minimum_order_value",
                ),
            },
        ),
        (
            "Público",
            {
                "fields": (
                    "audience_type",
                    "inactive_days",
                    "minimum_orders",
                    "minimum_spent",
                ),
                "description": (
                    "Configure quem pode utilizar este cupom. "
                    "Alguns campos só são utilizados para públicos específicos."
                ),
            },
        ),
        (
            "Período de validade",
            {
                "fields": (
                    "starts_at",
                    "ends_at",
                ),
            },
        ),
        (
            "Limites de utilização",
            {
                "fields": (
                    "usage_limit",
                    "usage_limit_per_customer",
                ),
            },
        ),
        (
            "Resultados",
            {
                "fields": (
                    "total_redemptions",
                    "total_discount_given",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
        (
            "Controle",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    inlines = [
        CouponAssignmentInline,
    ]

    actions = [
        "activate_campaigns",
        "deactivate_campaigns",
    ]

    # ------------------------------------------------------------------
    # Queryset
    # ------------------------------------------------------------------

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        tenant = getattr(
            request,
            "tenant",
            None,
        )

        if tenant is None:
            return queryset.none()

        return (
            queryset
            .filter(tenant=tenant)
            .annotate(
                redemptions_count=Count(
                    "redemptions",
                    distinct=True,
                ),
                discount_total=Sum(
                    "redemptions__discount_amount",
                ),
            )
        )

    # ------------------------------------------------------------------
    # Código
    # ------------------------------------------------------------------

    def code_display(self, obj):
        return format_html(
            (
                '<span style="'
                'font-family:monospace;'
                'font-size:12px;'
                'font-weight:800;'
                'padding:5px 9px;'
                'border-radius:8px;'
                'background:#f3f4f6;'
                'color:#111827;'
                '">'
                '{}'
                '</span>'
            ),
            obj.code,
        )

    code_display.short_description = "Código"

    # ------------------------------------------------------------------
    # Desconto
    # ------------------------------------------------------------------

    def discount_display(self, obj):
        if obj.discount_type == DiscountType.PERCENTAGE:
            return f"{obj.discount_value}%"

        if obj.discount_type == DiscountType.FIXED_AMOUNT:
            return (
                f"R$ {obj.discount_value:.2f}"
                .replace(".", ",")
            )

        if obj.discount_type == DiscountType.FREE_DELIVERY:
            return "Frete grátis"

        return "-"

    discount_display.short_description = "Desconto"

    # ------------------------------------------------------------------
    # Público
    # ------------------------------------------------------------------

    def audience_display(self, obj):
        label = obj.get_audience_type_display()

        if (
            obj.audience_type == AudienceType.INACTIVE
            and obj.inactive_days
        ):
            return f"{label} • {obj.inactive_days} dias"

        if (
            obj.audience_type == AudienceType.FREQUENT
            and obj.minimum_orders
        ):
            return (
                f"{label} • "
                f"{obj.minimum_orders}+ pedidos"
            )

        return label

    audience_display.short_description = "Público"

    # ------------------------------------------------------------------
    # Período
    # ------------------------------------------------------------------

    def period_display(self, obj):
        start = obj.starts_at.strftime("%d/%m/%Y")

        if obj.ends_at:
            end = obj.ends_at.strftime("%d/%m/%Y")
            return f"{start} → {end}"

        return f"{start} → Sem término"

    period_display.short_description = "Validade"

    # ------------------------------------------------------------------
    # Utilizações
    # ------------------------------------------------------------------

    def usage_display(self, obj):
        count = getattr(
            obj,
            "redemptions_count",
            0,
        )

        if obj.usage_limit:
            return (
                f"{count} / "
                f"{obj.usage_limit}"
            )

        return str(count)

    usage_display.short_description = "Utilizações"

    # ------------------------------------------------------------------
    # Status visual
    # ------------------------------------------------------------------

    def status_badge(self, obj):
        now = timezone.now()

        if not obj.is_active:
            label = "Inativo"
            color = "#6b7280"

        elif now < obj.starts_at:
            label = "Agendado"
            color = "#3b82f6"

        elif obj.ends_at and now > obj.ends_at:
            label = "Encerrado"
            color = "#dc2626"

        else:
            label = "Ativo"
            color = "#16a34a"

        return format_html(
            (
                '<span style="'
                'display:inline-flex;'
                'align-items:center;'
                'padding:4px 10px;'
                'border-radius:9999px;'
                'font-size:11px;'
                'font-weight:700;'
                'background:{}1a;'
                'color:{};'
                '">'
                '{}'
                '</span>'
            ),
            color,
            color,
            label,
        )

    status_badge.short_description = "Status"

    # ------------------------------------------------------------------
    # Métricas
    # ------------------------------------------------------------------

    def total_redemptions(self, obj):
        if not obj.pk:
            return "0"

        return obj.redemptions.count()

    total_redemptions.short_description = (
        "Total de utilizações"
    )

    def total_discount_given(self, obj):
        if not obj.pk:
            return "R$ 0,00"

        total = (
            obj.redemptions.aggregate(
                total=Sum(
                    "discount_amount"
                )
            )["total"]
            or 0
        )

        return (
            f"R$ {total:.2f}"
            .replace(".", ",")
        )

    total_discount_given.short_description = (
        "Desconto concedido"
    )

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------

    def activate_campaigns(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            is_active=True,
        )

        self.message_user(
            request,
            (
                f"{updated} campanha(s) "
                "ativada(s) com sucesso."
            ),
            messages.SUCCESS,
        )

    activate_campaigns.short_description = (
        "Ativar campanhas selecionadas"
    )

    def deactivate_campaigns(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            is_active=False,
        )

        self.message_user(
            request,
            (
                f"{updated} campanha(s) "
                "desativada(s) com sucesso."
            ),
            messages.SUCCESS,
        )

    deactivate_campaigns.short_description = (
        "Desativar campanhas selecionadas"
    )

    def save_model(self, request, obj, form, change):
        if not obj.tenant_id:
            obj.tenant = request.tenant

        super().save_model(
            request,
            obj,
            form,
            change,
        )


class CouponRedemptionAdmin(TenantPermissionMixin, ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not tenant_admin_allowed(request):
            return qs.none()
        return qs.filter(campaign__tenant=request.tenant, order__tenant=request.tenant)

    def has_view_permission(self, request, obj=None):
        return tenant_admin_allowed(request) and (obj is None or self.get_queryset(request).filter(pk=obj.pk).exists())

    list_display = (
        "campaign",
        "customer_display",
        "order_display",
        "discount_display",
        "redeemed_at",
    )

    search_fields = (
        "campaign__code",
        "campaign__name",
        "customer__user__first_name",
        "customer__user__last_name",
        "customer__user__email",
        "order__id",
    )

    list_filter = (
        ("campaign", admin.RelatedOnlyFieldListFilter),
        "redeemed_at",
    )

    ordering = (
        "-redeemed_at",
    )

    readonly_fields = (
        "campaign",
        "customer",
        "order",
        "discount_amount",
        "redeemed_at",
    )

    date_hierarchy = "redeemed_at"

    list_per_page = 25

    def has_add_permission(
        self,
        request,
    ):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def customer_display(self, obj):
        return str(obj.customer)

    customer_display.short_description = "Cliente"

    def order_display(self, obj):
        return f"#{obj.order_id}"

    order_display.short_description = "Pedido"

    def discount_display(self, obj):
        return (
            f"R$ {obj.discount_amount:.2f}"
            .replace(".", ",")
        )

    discount_display.short_description = "Desconto"


tenant_admin_site.register(
    CouponCampaign,
    CouponCampaignAdmin,
)

tenant_admin_site.register(
    CouponRedemption,
    CouponRedemptionAdmin,
)
