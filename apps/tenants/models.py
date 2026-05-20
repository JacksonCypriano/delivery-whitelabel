import re

from django.core.exceptions import ValidationError
from django.db import models

from .choices import SaleMode
from .utils import validate_whatsapp_number


class Tenant(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    whatsapp_number = models.CharField(max_length=13, unique=True, validators=[validate_whatsapp_number], verbose_name="Formato: 5511999999999")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sale_mode = models.CharField(max_length=20, choices=SaleMode.choices, default=SaleMode.WHATSAPP,
        verbose_name="Define se a loja aceita pagamentos online ou apenas pedidos pelo WhatsApp."
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.whatsapp_number = re.sub(r'\D', '', self.whatsapp_number)
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = "Loja"
        verbose_name_plural = "Lojas"
        ordering = ["name"]

class BrandConfig(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='brand_config')

    primary_color = models.CharField(max_length=7, default="#e74c3c", verbose_name="Cor principal (botões, links)")
    secondary_color = models.CharField(max_length=7, default="#2c3e50", verbose_name="Cor secundária (headers, ícones)")

    accent_color = models.CharField(max_length=7, default="#f39c12", verbose_name="Cor de destaque (badges, promoções)")
    background_color = models.CharField(max_length=7, default="#ffffff", verbose_name="Cor de fundo do site")
    text_color = models.CharField(max_length=7, default="#111827", verbose_name="Cor base do texto")

    dark_mode_primary = models.CharField(max_length=7, default="#3b82f6", verbose_name="Cor primária no modo escuro")
    dark_mode_background = models.CharField(max_length=7, default="#0f172a", verbose_name="Fundo no modo escuro")
    dark_mode_text = models.CharField(max_length=7, default="#f1f5f9", verbose_name="Texto no modo escuro")

    logo = models.ImageField(upload_to='logos/', blank=True, null=True, verbose_name="Logo da loja (recomendada: 200x200px)")
    favicon = models.ImageField(upload_to='favicons/', blank=True, null=True, verbose_name="Favicon da loja")
    banner = models.ImageField(upload_to='banners/', blank=True, null=True, verbose_name="Banner da loja")

    def __str__(self):
        return f"Config de Branding - {self.tenant.name}"

    class Meta:
        verbose_name = "Configuração de Marca"
        verbose_name_plural = "Configurações de Marca"
        ordering = ["tenant__name"]
