from django.contrib import admin, messages
from django.template.response import TemplateResponse
from datetime import timedelta

from django.db.models import Avg, Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.html import format_html

from apps.core.admin import TenantModelAdmin, TenantInlineMixin
from apps.tenants.admin_site import tenant_admin_site
from unfold.admin import TabularInline

from .models import Order, OrderItem


class OrderItemInline(TenantInlineMixin, TabularInline):
    tenant_lookup = "order__tenant"
    model = OrderItem
    extra = 0
    can_delete = False

    fields = (
        "name",
        "quantity",
        "price",
        "line_total",
    )

    readonly_fields = fields

    def has_add_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def line_total(self, obj):
        return (
            f"R$ {obj.get_total_price():.2f}"
            .replace(".", ",")
        )


class OrderAdmin(TenantModelAdmin):
    change_list_template = (
        "admin/orders/order/change_list.html"
    )

    list_display = (
        "order_number",
        "customer_display",
        "customer_phone",
        "items_summary",
        "total_display",
        "delivery_display",
        "whatsapp_badge",
        "status",
        "created_at",
    )

    list_filter = (
        "delivery_type",
        "payment_method",
        "created_at",
        "delivery_city",
        "delivery_neighborhood",
    )

    search_fields = (
        "id",
        "customer_name",
        "customer_phone",
        "coupon_code",
        "delivery_street",
        "delivery_neighborhood",
        "delivery_city",
    )

    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 25
    inlines = [OrderItemInline]

    readonly_fields = (
        "status",
        "customer",
        "customer_name",
        "customer_phone",
        "subtotal",
        "delivery_fee",
        "coupon_code",
        "discount_amount",
        "total",
        "delivery_type",
        "payment_method",
        "payment_change_for",
        "whatsapp_opened_at",
        "created_at",
        "delivery_zip_code",
        "delivery_street",
        "delivery_number",
        "delivery_complement",
        "delivery_neighborhood",
        "delivery_city",
        "delivery_state",
        "delivery_reference",
    )

    fieldsets = (
        (
            "Cliente",
            {
                "fields": (
                    "customer",
                    "customer_name",
                    "customer_phone",
                )
            },
        ),
        (
            "Venda gerada",
            {
                "fields": (
                    "delivery_type",
                    "status",
                    "payment_method",
                    "payment_change_for",
                    "subtotal",
                    "delivery_fee",
                    "coupon_code",
                    "discount_amount",
                    "total",
                    "whatsapp_opened_at",
                    "created_at",
                )
            },
        ),
        (
            "Endereço",
            {
                "fields": (
                    "delivery_zip_code",
                    "delivery_street",
                    "delivery_number",
                    "delivery_complement",
                    "delivery_neighborhood",
                    "delivery_city",
                    "delivery_state",
                    "delivery_reference",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ['cancel_orders']

    @admin.action(description='Cancelar pedidos e devolver estoque')
    def cancel_orders(self, request, queryset):
        if not request.POST.get('confirm_cancel'):
            return TemplateResponse(request, 'admin/orders/order/confirm_cancel.html', {
                **self.admin_site.each_context(request),
                'title': 'Confirmar cancelamento de pedidos',
                'orders': queryset, 'opts': self.model._meta,
                'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            })
        from .inventory import cancel
        count = sum(cancel(order_id, request.tenant) for order_id in queryset.order_by('pk').values_list('pk', flat=True))
        self.message_user(request, f'{count} pedido(s) cancelado(s). O estoque baixado foi devolvido quando ainda está controlado.', messages.SUCCESS)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(abandoned_at__isnull=True)
            .prefetch_related("items")
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def changelist_view(
        self,
        request,
        extra_context=None,
    ):
        now = timezone.now()
        since = now - timedelta(days=30)

        qs = (
            self.get_queryset(request)
            .filter(created_at__gte=since)
        )

        metrics = qs.aggregate(
            generated=Count("id"),
            whatsapp_opened=Count(
                "id",
                filter=__import__(
                    "django.db.models",
                    fromlist=["Q"],
                ).Q(
                    whatsapp_opened_at__isnull=False
                ),
            ),
            revenue=Sum("total"),
            avg_ticket=Avg("total"),
        )

        generated = metrics["generated"] or 0
        opened = metrics["whatsapp_opened"] or 0

        metrics["conversion"] = (
            round((opened / generated) * 100, 1)
            if generated
            else 0
        )
        metrics["revenue"] = (
            metrics["revenue"] or 0
        )
        metrics["avg_ticket"] = (
            metrics["avg_ticket"] or 0
        )

        top_products = (
            OrderItem.objects
            .filter(
                order__in=qs,
            )
            .values("name")
            .annotate(
                quantity=Sum("quantity"),
            )
            .order_by("-quantity", "name")[:5]
        )

        extra_context = {
            **(extra_context or {}),
            "sales_metrics": metrics,
            "top_products": top_products,
        }

        return super().changelist_view(
            request,
            extra_context=extra_context,
        )

    def order_number(self, obj):
        return f"#{obj.id}"

    def customer_display(self, obj):
        return (
            obj.customer_name
            or (
                str(obj.customer)
                if obj.customer
                else "Cliente"
            )
        )

    def total_display(self, obj):
        return (
            f"R$ {obj.total:.2f}"
            .replace(".", ",")
        )

    def delivery_display(self, obj):
        return obj.delivery_type_label

    def whatsapp_badge(self, obj):
        if obj.status == 'cancelled':
            return 'Cancelado'
        if obj.whatsapp_opened_at:
            return format_html(
                '<span style="font-weight:700;color:#16a34a;">WhatsApp aberto</span>'
            )

        return format_html(
            '<span style="font-weight:700;color:#d97706;">Gerado</span>'
        )

    def items_summary(self, obj):
        items = list(obj.items.all()[:4])

        if not items:
            return "-"

        parts = [
            f"{item.quantity}x {item.name}"
            for item in items[:3]
        ]

        if len(items) > 3:
            parts.append("…")

        return ", ".join(parts)


tenant_admin_site.register(
    Order,
    OrderAdmin,
)
