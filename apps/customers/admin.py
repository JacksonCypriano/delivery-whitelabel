from apps.core.admin import tenant_admin_allowed
from django.db.models import Count, Max, Q, Sum
from django.utils.html import format_html

from unfold.admin import ModelAdmin

from apps.orders.models import Order
from apps.tenants.admin_site import tenant_admin_site

from .models import Customer


class CustomerAdmin(ModelAdmin):
    list_display = (
        "customer_name",
        "email",
        "phone",
        "orders_count",
        "total_spent",
        "last_order",
        "customer_status",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "phone",
    )

    ordering = (
        "user__first_name",
        "user__last_name",
    )

    list_per_page = 25

    readonly_fields = (
        "customer_name_detail",
        "email_detail",
        "phone",
        "orders_count_detail",
        "total_spent_detail",
        "last_order_detail",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Dados do cliente",
            {
                "fields": (
                    "customer_name_detail",
                    "email_detail",
                    "phone",
                ),
            },
        ),
        (
            "Relacionamento com a loja",
            {
                "fields": (
                    "orders_count_detail",
                    "total_spent_detail",
                    "last_order_detail",
                ),
            },
        ),
        (
            "Cadastro",
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

    # --------------------------------------------------------------
    # Cada loja só enxerga clientes que compraram nela.
    # --------------------------------------------------------------

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
            .filter(
                orders__tenant=tenant,
            )
            .annotate(
                tenant_orders_count=Count(
                    "orders",
                    filter=Q(
                        orders__tenant=tenant,
                    ),
                    distinct=True,
                ),
                tenant_total_spent=Sum(
                    "orders__total",
                    filter=Q(
                        orders__tenant=tenant,
                    ),
                ),
                tenant_last_order=Max(
                    "orders__created_at",
                    filter=Q(
                        orders__tenant=tenant,
                    ),
                ),
            )
            .distinct()
        )

    def has_module_permission(self, request):
        return tenant_admin_allowed(request)

    def has_view_permission(self, request, obj=None):
        return tenant_admin_allowed(request) and (obj is None or self.get_queryset(request).filter(pk=obj.pk).exists())

    # --------------------------------------------------------------
    # Não permitimos criar Customer pelo admin da loja.
    # O consumidor se cadastra pelo site.
    # --------------------------------------------------------------

    def has_add_permission(self, request):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        # Dados do consumidor não devem ser alterados
        # diretamente pela loja.
        return False

    # --------------------------------------------------------------
    # Nome
    # --------------------------------------------------------------

    def customer_name(self, obj):
        return (
            obj.user.get_full_name()
            or obj.user.username
        )

    customer_name.short_description = "Cliente"
    customer_name.admin_order_field = "user__first_name"

    def customer_name_detail(self, obj):
        return self.customer_name(obj)

    customer_name_detail.short_description = "Nome"

    # --------------------------------------------------------------
    # E-mail
    # --------------------------------------------------------------

    def email(self, obj):
        return obj.user.email or "-"

    email.short_description = "E-mail"
    email.admin_order_field = "user__email"

    def email_detail(self, obj):
        return self.email(obj)

    email_detail.short_description = "E-mail"

    # --------------------------------------------------------------
    # Pedidos
    # --------------------------------------------------------------

    def orders_count(self, obj):
        return getattr(
            obj,
            "tenant_orders_count",
            0,
        )

    orders_count.short_description = "Pedidos"
    orders_count.admin_order_field = (
        "tenant_orders_count"
    )

    def orders_count_detail(self, obj):
        return self.orders_count(obj)

    orders_count_detail.short_description = (
        "Quantidade de pedidos"
    )

    # --------------------------------------------------------------
    # Total gasto
    # --------------------------------------------------------------

    def total_spent(self, obj):
        value = (
            getattr(
                obj,
                "tenant_total_spent",
                None,
            )
            or 0
        )

        return (
            f"R$ {value:.2f}"
            .replace(".", ",")
        )

    total_spent.short_description = "Total gasto"
    total_spent.admin_order_field = (
        "tenant_total_spent"
    )

    def total_spent_detail(self, obj):
        return self.total_spent(obj)

    total_spent_detail.short_description = (
        "Total gasto nesta loja"
    )

    # --------------------------------------------------------------
    # Último pedido
    # --------------------------------------------------------------

    def last_order(self, obj):
        value = getattr(
            obj,
            "tenant_last_order",
            None,
        )

        if not value:
            return "-"

        return value.strftime(
            "%d/%m/%Y %H:%M"
        )

    last_order.short_description = "Último pedido"
    last_order.admin_order_field = (
        "tenant_last_order"
    )

    def last_order_detail(self, obj):
        return self.last_order(obj)

    last_order_detail.short_description = (
        "Último pedido nesta loja"
    )

    # --------------------------------------------------------------
    # Status visual do relacionamento
    # --------------------------------------------------------------

    def customer_status(self, obj):
        count = getattr(
            obj,
            "tenant_orders_count",
            0,
        )

        if count >= 5:
            label = "Cliente frequente"
            color = "#16a34a"

        elif count >= 2:
            label = "Recorrente"
            color = "#3b82f6"

        else:
            label = "Novo cliente"
            color = "#f59e0b"

        return format_html(
            (
                '<span style="'
                'display:inline-flex;'
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

    customer_status.short_description = "Perfil"


tenant_admin_site.register(
    Customer,
    CustomerAdmin,
)
