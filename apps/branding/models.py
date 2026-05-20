from apps.core.models import TenantModel
from django.db import models


class BrandConfig(TenantModel):
    logo = models.ImageField(upload_to='logos/', blank=True, verbose_name="Logo da loja (recomendada: 200x200px)")
    primary_color = models.CharField(max_length=7, default='#000000', verbose_name="Cor principal (botões, links)")
    secondary_color = models.CharField(max_length=7, default='#FFFFFF', verbose_name="Cor secundária (headers, ícones)")
