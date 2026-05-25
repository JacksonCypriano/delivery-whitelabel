from django.contrib import admin, messages
from apps.core.admin import TenantModelAdmin
from apps.tenants.admin_site import tenant_admin_site

from .models import Category, CustomizationGroup, CustomizationOption, HalfProduct, Product, ProductImage


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


# ── Customizações ─────────────────────────────────────────────────────────────

class CustomizationOptionInline(admin.TabularInline):
    model = CustomizationOption
    extra = 1
    fields = ('name', 'description', 'price', 'image', 'is_available', 'order')
    ordering = ('order',)


@admin.register(CustomizationGroup, site=tenant_admin_site)
class CustomizationGroupAdmin(TenantModelAdmin):
    list_display = ('name', 'category', 'apply_to_display', 'min_options', 'max_options', 'is_active', 'order')
    list_filter = ('category', 'apply_to', 'is_active')
    search_fields = ('name',)
    ordering = ('category', 'order')
    inlines = [CustomizationOptionInline]

    fieldsets = (
        (None, {
            'fields': ('category', 'name', 'apply_to', 'is_active', 'order')
        }),
        ('Limites de seleção', {
            'description': 'Defina quantas opções o cliente pode/deve escolher neste grupo.',
            'fields': ('min_options', 'max_options'),
        }),
    )

    def apply_to_display(self, obj):
        return obj.get_apply_to_display()
    apply_to_display.short_description = 'Aplica-se a'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == 'category':
            tenant = getattr(request, 'tenant', None)
            if tenant:
                field.queryset = field.queryset.filter(tenant=tenant)
        return field
