import re

from django.db import transaction
from rest_framework import serializers

from .models import BrandConfig, BusinessHour, Tenant


class BrandConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandConfig
        fields = [
            'logo', 'favicon', 'banner', 'primary_color', 'secondary_color',
            'accent_color', 'background_color', 'text_color',
            'dark_mode_primary', 'dark_mode_background', 'dark_mode_text',
        ]


class BusinessHourSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessHour
        fields = ['weekday', 'is_closed', 'opening_time', 'closing_time']

    def validate(self, attrs):
        if not attrs.get('is_closed', True):
            opening, closing = attrs.get('opening_time'), attrs.get('closing_time')
            if not opening or not closing or opening == closing:
                raise serializers.ValidationError('Informe abertura e fechamento diferentes ou marque como fechado.')
        return attrs


class TenantCreateSerializer(serializers.ModelSerializer):
    brand = BrandConfigSerializer(source='brand_config', required=False)
    business_hours = BusinessHourSerializer(many=True, required=False)

    class Meta:
        model = Tenant
        fields = [
            'id', 'name', 'slug', 'whatsapp_number', 'sale_mode', 'fulfillment_mode',
            'is_active', 'pickup_address', 'pickup_number', 'pickup_complement',
            'pickup_neighborhood', 'pickup_city', 'pickup_zip_code',
            'business_hours', 'brand',
        ]
        read_only_fields = ['id']

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: 'Campo não reconhecido.' for key in unknown})
        data = data.copy()
        if isinstance(data.get('whatsapp_number'), str):
            data['whatsapp_number'] = re.sub(r'\D', '', data['whatsapp_number'])
        return super().to_internal_value(data)

    @transaction.atomic
    def create(self, validated_data):
        brand_data = validated_data.pop('brand_config', {})
        hours = validated_data.pop('business_hours', None)
        tenant = Tenant.objects.create(**validated_data)
        BrandConfig.objects.create(tenant=tenant, **brand_data)
        if hours is not None:
            tenant.business_hours.all().delete()
            for hour in hours:
                BusinessHour.objects.create(tenant=tenant, **hour)
        return tenant
