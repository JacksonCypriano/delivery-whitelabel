from rest_framework import serializers
from .models import Tenant
from apps.branding.models import BrandConfig

class BrandConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandConfig
        fields = ['logo', 'primary_color', 'secondary_color', 'accent_color', 'background_color', 'text_color', 'dark_mode_primary', 'dark_mode_background', 'dark_mode_text']

class TenantCreateSerializer(serializers.ModelSerializer):
    brand = BrandConfigSerializer()

    class Meta:
        model = Tenant
        fields = ['name', 'slug', 'whatsapp_instance_key', 'whatsapp_api_key', 'brand']

    def create(self, validated_data):
        brand_data = validated_data.pop('brand')
        tenant = Tenant.objects.create(**validated_data)
        BrandConfig.objects.create(tenant=tenant, **brand_data)
        return tenant
