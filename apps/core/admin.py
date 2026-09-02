"""Tenant-bound admin permissions, forms and related objects."""
from django.core.exceptions import PermissionDenied, ValidationError
from unfold.admin import ModelAdmin


def tenant_admin_allowed(request):
    user = request.user
    tenant = getattr(request, 'tenant', None)
    return bool(tenant and user.is_authenticated and user.is_active and user.is_staff
                and user.is_tenant_admin and not user.is_superuser
                and user.tenant_id == tenant.pk)


def belongs_to_tenant(obj, tenant):
    if obj is None:
        return True
    if obj._meta.label_lower == 'tenants.tenant':
        return obj.pk == tenant.pk
    return getattr(obj, 'tenant_id', None) == tenant.pk


class TenantPermissionMixin:
    def has_module_permission(self, request):
        return tenant_admin_allowed(request)

    def has_view_permission(self, request, obj=None):
        return tenant_admin_allowed(request) and belongs_to_tenant(obj, request.tenant)

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)


class TenantRelatedFieldsMixin:
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if field is None or field.queryset is None:
            return field
        tenant = getattr(request, 'tenant', None)
        model = field.queryset.model
        names = {f.name for f in model._meta.fields}
        if not tenant_admin_allowed(request):
            field.queryset = field.queryset.none()
        elif model._meta.label_lower == 'tenants.tenant':
            field.queryset = field.queryset.filter(pk=tenant.pk)
        elif 'tenant' in names:
            field.queryset = field.queryset.filter(tenant=tenant)
        elif model._meta.label_lower == 'customers.customer':
            field.queryset = field.queryset.filter(orders__tenant=tenant).distinct()
        return field

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if field is not None and hasattr(field.queryset.model, 'tenant'):
            field.queryset = (field.queryset.filter(tenant=request.tenant)
                              if tenant_admin_allowed(request) else field.queryset.none())
        return field


class TenantModelAdmin(TenantPermissionMixin, TenantRelatedFieldsMixin, ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(tenant=request.tenant) if tenant_admin_allowed(request) else qs.none()

    def get_exclude(self, request, obj=None):
        return tuple(super().get_exclude(request, obj) or ()) + ('tenant',)

    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, **kwargs)
        tenant = getattr(request, 'tenant', None)

        class BoundTenantForm(base):
            def __init__(self, *args, **form_kwargs):
                super().__init__(*args, **form_kwargs)
                self.instance.tenant = tenant

            def _post_clean(self):
                super()._post_clean()
                if not self.errors:
                    try:
                        self.instance.validate_unique()
                        self.instance.validate_constraints()
                    except ValidationError as exc:
                        self.add_error(None, ValidationError(exc.messages))

        return BoundTenantForm

    def save_model(self, request, obj, form, change):
        if not tenant_admin_allowed(request):
            raise PermissionDenied
        if change and not self.model.objects.filter(pk=obj.pk, tenant=request.tenant).exists():
            raise PermissionDenied
        obj.tenant = request.tenant
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        if not tenant_admin_allowed(request) or not belongs_to_tenant(form.instance, request.tenant):
            raise PermissionDenied
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for obj in instances:
            if hasattr(obj, 'tenant_id'):
                if obj.pk and not type(obj).objects.filter(pk=obj.pk, tenant=request.tenant).exists():
                    raise PermissionDenied
                obj.tenant = request.tenant
            obj.save()
        formset.save_m2m()


class TenantInlineMixin(TenantPermissionMixin, TenantRelatedFieldsMixin):
    """Permissions apply to the parent; querysets also constrain forged inline IDs."""
    tenant_lookup = 'tenant'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(**{self.tenant_lookup: request.tenant}) if tenant_admin_allowed(request) else qs.none()

    def get_formset(self, request, obj=None, **kwargs):
        base = super().get_formset(request, obj, **kwargs)
        tenant = getattr(request, 'tenant', None)

        class BoundTenantFormSet(base):
            def _construct_form(self, i, **form_kwargs):
                form = super()._construct_form(i, **form_kwargs)
                pk_name = self.model._meta.pk.name
                if pk_name in form.fields and hasattr(form.fields[pk_name], 'queryset'):
                    form.fields[pk_name].queryset = self.get_queryset()
                if hasattr(form.instance, 'tenant_id'):
                    form.instance.tenant = tenant
                return form

        return BoundTenantFormSet
