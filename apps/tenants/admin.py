from django.contrib import admin
from .models import Tenant, BrandConfig
from .admin_site import tenant_admin_site

@admin.register(Tenant, site=tenant_admin_site)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'created_at')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(BrandConfig, site=tenant_admin_site)
class BrandConfigAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'primary_color', 'secondary_color')


from django.contrib import admin as dj_admin

dj_admin.site.register(Tenant, TenantAdmin)
dj_admin.site.register(BrandConfig, BrandConfigAdmin)