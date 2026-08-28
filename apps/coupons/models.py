from django.db import models
from django.utils import timezone

from apps.tenants.models import Tenant


class DiscountType(models.TextChoices):
    PERCENTAGE = "percentage", "Percentual"
    FIXED_AMOUNT = "fixed_amount", "Valor fixo"
    FREE_DELIVERY = "free_delivery", "Frete grátis"


class AudienceType(models.TextChoices):
    ALL = "all", "Todos os clientes"
    FIRST_ORDER = "first_order", "Primeira compra"
    INACTIVE = "inactive", "Clientes inativos"
    SPECIFIC = "specific", "Clientes específicos"
    FREQUENT = "frequent", "Clientes frequentes"
    NEVER_ORDERED = "never_ordered", "Nunca compraram nesta loja"


class CouponCampaign(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="coupon_campaigns",
        verbose_name="Loja",
    )

    name = models.CharField(
        max_length=120,
        verbose_name="Nome da campanha",
    )

    code = models.CharField(
        max_length=40,
        verbose_name="Código do cupom",
    )

    discount_type = models.CharField(
        max_length=20,
        choices=DiscountType.choices,
        verbose_name="Tipo de desconto",
    )

    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Valor do desconto",
    )

    minimum_order_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Valor mínimo do pedido",
    )

    audience_type = models.CharField(
        max_length=30,
        choices=AudienceType.choices,
        default=AudienceType.ALL,
        verbose_name="Público da campanha",
    )

    inactive_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Dias sem comprar",
    )

    minimum_orders = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Quantidade mínima de pedidos",
    )

    minimum_spent = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Valor mínimo já gasto",
    )

    starts_at = models.DateTimeField(
        default=timezone.now,
        blank=True,
        verbose_name="Início da campanha",
        help_text="Se deixar em branco, a campanha começa imediatamente.",
    )

    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fim da campanha",
        help_text="Deixe em branco para uma campanha sem data de encerramento.",
    )

    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Limite total de utilizações",
    )

    usage_limit_per_customer = models.PositiveIntegerField(
        default=1,
        verbose_name="Limite de uso por cliente",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Ativo",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Atualizado em",
    )

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()

        if not self.starts_at:
            self.starts_at = timezone.now()

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Campanha de cupom"
        verbose_name_plural = "Campanhas de cupons"

        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_coupon_code_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class CouponAssignment(models.Model):
    campaign = models.ForeignKey(
        CouponCampaign,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="Campanha",
    )

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="coupon_assignments",
        verbose_name="Cliente",
    )

    assigned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Atribuído em",
    )

    class Meta:
        verbose_name = "Cliente da campanha"
        verbose_name_plural = "Clientes da campanha"

        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "customer"],
                name="unique_customer_per_campaign",
            ),
        ]

    def __str__(self):
        return f"{self.customer} - {self.campaign.code}"


class CouponRedemption(models.Model):
    campaign = models.ForeignKey(
        CouponCampaign,
        on_delete=models.PROTECT,
        related_name="redemptions",
        verbose_name="Campanha",
    )

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="coupon_redemptions",
        verbose_name="Cliente",
    )

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="coupon_redemption",
        verbose_name="Pedido",
    )

    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Valor do desconto",
    )

    redeemed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Utilizado em",
    )

    class Meta:
        verbose_name = "Uso de cupom"
        verbose_name_plural = "Usos de cupons"

    def __str__(self):
        return (
            f"{self.campaign.code} - "
            f"Pedido #{self.order_id}"
        )
