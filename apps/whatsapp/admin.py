from apps.tenants.admin_site import tenant_admin_site
from django.contrib import admin
from .models import WhatsAppConfig

class WhatsAppConfigAdmin(admin.ModelAdmin):
    list_display = [
        'tenant',
        'display_phone_number',
        'phone_number_id',
        'is_active',
        'webhook_subscribed',
        'updated_at',
    ]
    list_filter = ['is_active', 'webhook_subscribed']
    search_fields = ['tenant__name', 'display_phone_number', 'phone_number_id']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Tenant', {
            'fields': ('tenant', 'is_active')
        }),
        ('Número Oficial', {
            'fields': ('display_phone_number', 'phone_number_id', 'business_account_id')
        }),
        ('Credenciais', {
            'fields': ('access_token', 'verify_token', 'app_secret'),
            'classes': ('collapse',),
        }),
        ('Webhook', {
            'fields': ('webhook_subscribed',)
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

tenant_admin_site.register(WhatsAppConfig, WhatsAppConfigAdmin)
