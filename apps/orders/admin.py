from django.contrib import messages
from django.utils.html import format_html

from apps.core.admin import TenantModelAdmin
from apps.tenants.admin_site import tenant_admin_site
from unfold.admin import TabularInline

from .choices import Status
from .models import Order, OrderItem

STATUS_COLORS = {
    Status.PENDING: "#f59e0b",
    Status.CONFIRMED: "#3b82f6",
    Status.DELIVERED: "#16a34a",
    Status.CANCELLED: "#dc2626",
}


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("name", "quantity", "price", "line_total")
    readonly_fields = ("name", "quantity", "price", "line_total")

    def has_add_permission(self, request, obj=None):
        return False

    def line_total(self, obj):
        try:
            return f"R$ {obj.price * obj.quantity:.2f}".replace(".", ",")
        except Exception:
            return "-"
    line_total.short_description = "Subtotal"


class OrderAdmin(TenantModelAdmin):
    list_display = ("order_number", "customer_phone", "items_summary", "total_display", "status_badge", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "customer_phone")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [OrderItemInline]
    readonly_fields = ("customer_phone", "total", "created_at")
    fields = ("customer_phone", "total", "status", "created_at")
    list_per_page = 25
    actions = ["mark_as_confirmed", "mark_as_delivered", "mark_as_cancelled"]

    # Pedidos são criados pelo fluxo de checkout — não pelo admin.
    def has_add_permission(self, request):
        return False

    def order_number(self, obj):
        return f"#{obj.id}"
    order_number.short_description = "Pedido"
    order_number.admin_order_field = "id"

    def total_display(self, obj):
        return f"R$ {obj.total:.2f}".replace(".", ",")
    total_display.short_description = "Total"
    total_display.admin_order_field = "total"

    def items_summary(self, obj):
        items = obj.items.all()
        if not items:
            return "-"
        parts = [f"{i.quantity}x {i.name}" for i in items[:3]]
        extra = items.count() - 3
        if extra > 0:
            parts.append(f"+{extra}")
        return ", ".join(parts)
    items_summary.short_description = "Itens"

    def status_badge(self, obj):
        color = STATUS_COLORS.get(obj.status, "#6b7280")
        return format_html(
            '<span class="order-status-badge" style="background:{}1a;color:{};">{}</span>',
            color, color, obj.get_status_display(),
        )
    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    # ── Ações em massa ──────────────────────────────────────────────────────
    def _bulk_update(self, request, queryset, new_status, label):
        updated = queryset.update(status=new_status)
        self.message_user(request, f"{updated} pedido(s) marcado(s) como {label}.", messages.SUCCESS)

    def mark_as_confirmed(self, request, queryset):
        self._bulk_update(request, queryset, Status.CONFIRMED, "Confirmado")
    mark_as_confirmed.short_description = "Marcar como Confirmado"

    def mark_as_delivered(self, request, queryset):
        self._bulk_update(request, queryset, Status.DELIVERED, "Entregue")
    mark_as_delivered.short_description = "Marcar como Entregue"

    def mark_as_cancelled(self, request, queryset):
        self._bulk_update(request, queryset, Status.CANCELLED, "Cancelado")
    mark_as_cancelled.short_description = "Marcar como Cancelado"


tenant_admin_site.register(Order, OrderAdmin)
