from django.contrib import admin

from apps.core.admin import TenantModelAdmin
from apps.tenants.admin_site import tenant_admin_site

from .models import Category, Product


@admin.register(Category, site=tenant_admin_site)
class CategoryAdmin(TenantModelAdmin):
    list_display = ('name', )

@admin.register(Product, site=tenant_admin_site)
class ProductAdmin(TenantModelAdmin):
    list_display = ('name', 'price')
