from django.contrib import admin, messages
from apps.core.admin import TenantModelAdmin
from apps.tenants.admin_site import tenant_admin_site

from .models import Category, Product, ProductImage, HalfProduct


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'alt_text', 'is_primary', 'order')
    show_change_link = True


@admin.register(Category, site=tenant_admin_site)
class CategoryAdmin(TenantModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product, site=tenant_admin_site)
class ProductAdmin(TenantModelAdmin):
    list_display = ('name', 'category', 'price', 'is_available', 'is_featured')
    search_fields = ('name', 'description', 'sku')
    list_filter = ('category', 'is_available', 'is_featured')
    inlines = [ProductImageInline]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ('created_at', 'updated_at')
    actions = ['create_half_for_selected']

    def create_half_for_selected(self, request, queryset):
        """
        Action do admin para criar HalfProduct para products selecionados que ainda não têm.
        """
        created_count = 0
        for product in queryset:
            half, created = HalfProduct.objects.get_or_create(product=product)
            if created:
                created_count += 1
        if created_count:
            self.message_user(request, f"{created_count} meio(s) criado(s).", messages.SUCCESS)
        else:
            self.message_user(request, "Nenhum meio criado (já existiam para os produtos selecionados).", messages.INFO)
    
    create_half_for_selected.short_description = "Criar HalfProduct para produtos selecionados"


@admin.register(HalfProduct, site=tenant_admin_site)
class HalfProductAdmin(TenantModelAdmin):
    list_display = ('product', 'is_active', 'created_at')
    search_fields = ('product__name',)
    list_filter = ('is_active',)
