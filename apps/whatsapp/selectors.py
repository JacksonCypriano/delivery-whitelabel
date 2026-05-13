from typing import Optional
from .models import WhatsAppConfig
from apps.tenants.models import Tenant

def get_whatsapp_config_for_tenant(tenant: Tenant) -> Optional[WhatsAppConfig]:

    return WhatsAppConfig.objects.filter(tenant=tenant, is_active=True).first()

def get_tenant_by_phone_number_id(phone_number_id: str) -> Optional[Tenant]:
    config = WhatsAppConfig.objects.filter(phone_number_id=phone_number_id, is_active=True).select_related('tenant').first()

    return config.tenant if config else None

def get_config_by_phone_number_id(phone_number_id: str) -> Optional[WhatsAppConfig]:

    return WhatsAppConfig.objects.filter(phone_number_id=phone_number_id, is_active=True).first()
