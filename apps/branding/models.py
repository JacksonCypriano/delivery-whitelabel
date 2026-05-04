from apps.core.models import TenantModel
from django.db import models


class BrandConfig(TenantModel):
    logo = models.ImageField(upload_to='logos/', blank=True)
    primary_color = models.CharField(max_length=7, default='#000000')
    secondary_color = models.CharField(max_length=7, default='#FFFFFF')
    custom_domain = models.CharField(max_length=255, blank=True)
