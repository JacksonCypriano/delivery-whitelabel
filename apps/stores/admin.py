from django.db import transaction
from django.db.models import Sum
from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html

from apps.core.admin import TenantModelAdmin, TenantInlineMixin
from apps.tenants.admin_site import tenant_admin_site

from .models import (
    DAYS_OF_WEEK,
    Category,
    CustomizationGroup,
    CustomizationGroupLabel,
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


class ProductImageInline(TenantInlineMixin, admin.TabularInline):
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
    list_display = ('thumbnail', 'name', 'category', 'price', 'is_available', 'is_featured', 'available_days_display')
    list_display_links = ('thumbnail', 'name')
    list_editable = ('is_available', 'is_featured')
    search_fields = ('name', 'description', 'sku')
    list_filter = (('category', admin.RelatedOnlyFieldListFilter), 'is_available', 'is_featured')
    inlines = [ProductImageInline]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ('created_at', 'updated_at', 'reserved_stock')
    actions = ['create_half_for_selected', 'mark_as_available', 'mark_as_unavailable']

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if change:
            # An unrelated edit must not overwrite a concurrent stock deduction
            # with the value read when the form was opened.
            current = Product.objects.select_for_update().get(pk=obj.pk, tenant=request.tenant)
            if 'stock' not in form.changed_data:
                obj.stock = current.stock
        super().save_model(request, obj, form, change)

    def reserved_stock(self, obj):
        if not obj.pk or obj.stock is None:
            return 'Sem controle de estoque'
        from apps.orders.inventory import active_reservations
        return active_reservations().filter(product=obj).aggregate(total=Sum('quantity'))['total'] or 0
    reserved_stock.short_description = 'Reservado em revisões válidas'

    def thumbnail(self, obj):
        url = obj.get_primary_image() if hasattr(obj, 'get_primary_image') else None
        if url:
            return format_html(
                '<img src="{}" style="width:44px;height:44px;object-fit:cover;border-radius:8px;border:1px solid #eee;">',
                url,
            )
        return format_html(
            '<div style="width:44px;height:44px;border-radius:8px;background:#f1f5f9;'
            'display:flex;align-items:center;justify-content:center;color:#94a3b8;font-size:11px;">—</div>'
        )
    thumbnail.short_description = "Imagem"

    def mark_as_available(self, request, queryset):
        updated = queryset.update(is_available=True)
        self.message_user(request, f"{updated} produto(s) marcado(s) como disponível.", messages.SUCCESS)
    mark_as_available.short_description = "Marcar como disponível"

    def mark_as_unavailable(self, request, queryset):
        updated = queryset.update(is_available=False)
        self.message_user(request, f"{updated} produto(s) marcado(s) como indisponível.", messages.SUCCESS)
    mark_as_unavailable.short_description = "Marcar como indisponível"

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


# ── Rótulos de Grupos de Personalização ───────────────────────────────────────

@admin.register(CustomizationGroupLabel, site=tenant_admin_site)
class CustomizationGroupLabelAdmin(TenantModelAdmin):
    list_display = ('name', 'groups_count')
    search_fields = ('name',)
    ordering = ('name',)

    def groups_count(self, obj):
        return obj.groups.count()
    groups_count.short_description = "Grupos usando este rótulo"


# ── Grupos de Personalização ──────────────────────────────────────────────────

class CustomizationOptionInline(TenantInlineMixin, admin.StackedInline):
    model = CustomizationOption
    extra = 1
    fields = ('name', 'description', 'price', 'image', 'is_available')
    ordering = ('name',)
    verbose_name = "Opção de Personalização"
    verbose_name_plural = "Opções de Personalização"


@admin.register(CustomizationGroup, site=tenant_admin_site)
class CustomizationGroupAdmin(TenantModelAdmin):
    list_display = ('label', 'category', 'apply_to_display', 'min_options', 'max_options', 'is_active')
    list_filter = (('category', admin.RelatedOnlyFieldListFilter), 'apply_to', 'is_active')
    search_fields = ('label__name', 'category__name')
    ordering = ('category', 'label__name')
    inlines = [CustomizationOptionInline]

    fieldsets = (
        (None, {
            'fields': ('category', 'label', 'apply_to', 'is_active')
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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        tenant = getattr(request, 'tenant', None)
        if tenant:
            if db_field.name == 'category':
                field.queryset = field.queryset.filter(tenant=tenant)
            elif db_field.name == 'label':
                field.queryset = field.queryset.filter(tenant=tenant)
        return field
