"""Superuser-only review interface; deliberately does not expose encrypted PII."""
from django.contrib import admin
from apps.tenants.admin_site import super_admin_site
from apps.channels.models import Food99StagedOrder, Food99StagedRevision


class SuperuserReadOnlyMixin:
    def has_module_permission(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RevisionInline(admin.TabularInline):
    model = Food99StagedRevision
    fields = ('version', 'status_code', 'fingerprint', 'created_at')
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Food99StagedOrder, site=super_admin_site)
class Food99StagedOrderAdmin(SuperuserReadOnlyMixin, admin.ModelAdmin):
    list_display = ('id', 'tenant_slug', 'external_id', 'state', 'last_seen_status',
                    'item_count', 'amount_minor', 'change_count', 'updated_at')
    list_filter = ('state', 'last_seen_status', 'connection__tenant')
    search_fields = ('external_id', 'app_shop_id', 'connection__merchant_id')
    readonly_fields = ('connection', 'external_id', 'app_shop_id', 'fingerprint',
                       'latest_fingerprint', 'last_seen_status', 'item_count',
                       'amount_minor', 'state', 'change_count', 'created_at', 'updated_at')
    exclude = ('encrypted_snapshot', 'latest_encrypted_snapshot')
    inlines = (RevisionInline,)
    list_select_related = ('connection__tenant',)

    @admin.display(description='Tenant')
    def tenant_slug(self, obj):
        return obj.connection.tenant.slug


@admin.register(Food99StagedRevision, site=super_admin_site)
class Food99StagedRevisionAdmin(SuperuserReadOnlyMixin, admin.ModelAdmin):
    list_display = ('staged_order', 'version', 'status_code', 'fingerprint', 'created_at')
    search_fields = ('staged_order__external_id',)
    readonly_fields = ('staged_order', 'version', 'status_code', 'fingerprint', 'created_at')
    exclude = ('encrypted_snapshot',)
    list_select_related = ('staged_order',)
