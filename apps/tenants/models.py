import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from .choices import SaleMode
from .utils import validate_whatsapp_number


class Tenant(models.Model):
    name = models.CharField(max_length=255, verbose_name="Nome da loja")
    slug = models.SlugField(unique=True, verbose_name="Identificador (subdomínio)")
    whatsapp_number = models.CharField(max_length=13, unique=True, validators=[validate_whatsapp_number], verbose_name="WhatsApp (formato: 5511999999999)")
    is_active = models.BooleanField(default=True, verbose_name="Loja ativa")
    created_at = models.DateTimeField(auto_now_add=True)
    sale_mode = models.CharField(max_length=20, choices=SaleMode.choices, default=SaleMode.WHATSAPP,
        verbose_name="Modo de venda",
        help_text="Define se a loja aceita pagamentos online ou apenas pedidos pelo WhatsApp."
    )

    # ── Informações da loja (white-label) ───────────────────────────────────
    address = models.CharField(
        max_length=255, blank=True, verbose_name="Endereço da loja",
        help_text="Endereço exibido no cardápio (opcional)."
    )
    business_hours = models.CharField(
        max_length=255, blank=True, verbose_name="Horário de funcionamento",
        help_text="Ex: Seg a Sáb, 18h às 23h."
    )
    delivery_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        verbose_name="Taxa de entrega",
        help_text="Valor cobrado pela entrega. Deixe 0 para entrega grátis."
    )
    delivery_time_estimate = models.CharField(
        max_length=60, blank=True, verbose_name="Tempo estimado de entrega",
        help_text="Ex: 30-45 min."
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
