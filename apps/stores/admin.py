from django.contrib import admin
from .models import Product, Category
from core.admin import TenantModelAdmin
from tenants.admin_site import tenant_admin_site

@admin.register(Category, site=tenant_admin_site)
class CategoryAdmin(TenantModelAdmin):
    list_display = ('name', )

@admin.register(Product, site=tenant_admin_site)
class ProductAdmin(TenantModelAdmin):
    list_display = ('name', 'price')
