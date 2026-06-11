from django import forms
from django.contrib import admin, messages

from apps.core.admin import TenantModelAdmin
from apps.tenants.admin_site import tenant_admin_site

from .models import (
    DAYS_OF_WEEK,
    Category,
    CustomizationGroup,
    CustomizationOption,
    HalfProduct,
    Product,
    ProductImage,
)


class ProductAdminForm(forms.ModelForm):
    available_days = forms.MultipleChoiceField(
        choices=DAYS_OF_WEEK,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Dias disponíveis",
        help_text="Selecione os dias em que este produto aparece. Deixe em branco para aparecer todos os dias."
    )

    class Meta:
        model = Product
        fields = '__all__'

    def clean_available_days(self):
        return [int(d) for d in self.cleaned_data.get('available_days', [])]


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
    form = ProductAdminForm
    list_display = ('name', 'category', 'price', 'is_available', 'is_featured', 'available_days_display')
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

    def available_days_display(self, obj):
        if not obj.available_days:
            return "Todos os dias"
        nomes = dict(DAYS_OF_WEEK)
        return ", ".join(nomes[d] for d in obj.available_days)

    available_days_display.short_description = "Dias disponíveis"


# ── Customizações ─────────────────────────────────────────────────────────────

class CustomizationOptionInline(admin.StackedInline):
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

    def save_model(self, request, obj, form, change):
        if not obj.tenant_id:
            obj.tenant = request.tenant
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        """
        Garante que as opções criadas via Inline (CustomizationOption) 
        também recebam o tenant da loja logada.
        """
        instances = formset.save(commit=False)

        for obj in formset.deleted_objects:
            obj.delete()

        for instance in instances:
            # Se for uma opção de customização e não tiver tenant, injeta o tenant logado
            if hasattr(instance, "tenant_id") and not instance.tenant_id:
                instance.tenant = request.tenant
            instance.save()
        
        formset.save_m2m()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == 'category':
            tenant = getattr(request, 'tenant', None)
            if tenant:
                field.queryset = field.queryset.filter(tenant=tenant)
        return field
