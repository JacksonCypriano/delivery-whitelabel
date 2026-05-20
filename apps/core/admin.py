from unfold.admin import ModelAdmin

class TenantModelAdmin(ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        tenant = getattr(request, 'tenant', None)
        if tenant:
            return qs.filter(tenant=tenant)
        return qs.none()

    def save_model(self, request, obj, form, change):
        if not change and hasattr(obj, 'tenant') and not obj.tenant_id:
            obj.tenant = request.tenant or request.user.tenant
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if request.user.is_superuser:
            return field
        tenant = getattr(request, 'tenant', None)
        if tenant and db_field.name in ('tenant', 'category', 'product'):
            field.queryset = field.queryset.filter(tenant=tenant)
        return field

    def has_module_permission(self, request):
        return True

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return True

    def has_delete_permission(self, request, obj=None):
        return True
