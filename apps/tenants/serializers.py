from rest_framework import serializers

from .models import BrandConfig, Tenant


class BrandConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandConfig
        fields = [
            'logo', 'favicon', 'banner',
            'primary_color', 'secondary_color', 'accent_color',
            'background_color', 'text_color',
            'dark_mode_primary', 'dark_mode_background', 'dark_mode_text',
        ]


class TenantCreateSerializer(serializers.ModelSerializer):
    brand = BrandConfigSerializer(required=False)

    class Meta:
        model = Tenant
        fields = [
            'id', 'name', 'slug', 'whatsapp_number', 'sale_mode',
            'address', 'business_hours', 'brand',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        brand_data = validated_data.pop('brand', None)
        tenant = Tenant.objects.create(**validated_data)
        # BrandConfig tem relação OneToOne com Tenant (related_name='brand_config')
        BrandConfig.objects.create(tenant=tenant, **(brand_data or {}))
        return tenant
