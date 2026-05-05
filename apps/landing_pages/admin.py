from django.contrib import admin
from .models import LandingPage, ThemeTemplate

@admin.register(LandingPage)
class LandingPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'tenant', 'is_active')
    prepopulated_fields = {'slug': ('title',)}

@admin.register(ThemeTemplate)
class ThemeTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'primary_color', 'accent_color')
    actions = ['apply_to_selected_tenants']

    def apply_to_selected_tenants(self, request, queryset):
        for theme in queryset:
            self.message_user(request, f"Tema '{theme.name}' aplicado!")
    apply_to_selected_tenants.short_description = "Aplicar tema selecionado"
