# tenants/admin_site.py
from django.contrib.admin import AdminSite
from django.template.response import TemplateResponse

class TenantAdminSite(AdminSite):
    site_title = "Painel"
    site_header = "Painel Admin"
    index_title = "Bem-vindo"

    def each_context(self, request):
        ctx = super().each_context(request)
        tenant = getattr(request, 'tenant', None)
        if tenant and hasattr(tenant, 'brandconfig'):
            brand = tenant.brandconfig
            ctx['tenant_brand'] = brand
            ctx['site_header'] = brand.tenant.name
        return ctx

    def has_permission(self, request):
        user = request.user
        if not user.is_active or not user.is_staff:
            return False

        if user.is_superuser:
            return True

        return getattr(request, 'tenant', None) and user.tenant_id == request.tenant.id

tenant_admin_site = TenantAdminSite(name='tenant_admin')
