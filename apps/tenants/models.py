import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .choices import SaleMode, FulfillmentMode
from .utils import validate_whatsapp_number


class Tenant(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name="Nome da loja"
    )

    slug = models.SlugField(
        unique=True,
        verbose_name="Identificador (subdomínio)"
    )

    whatsapp_number = models.CharField(
        max_length=13,
        unique=True,
        validators=[validate_whatsapp_number],
        verbose_name="WhatsApp (formato: 5511999999999)"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Loja ativa"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    sale_mode = models.CharField(
        max_length=20,
        choices=SaleMode.choices,
        default=SaleMode.WHATSAPP,
        verbose_name="Modo de venda",
        help_text=(
            "Define se a loja aceita pagamentos online "
            "ou apenas pedidos pelo WhatsApp."
        )
    )

    # ─────────────────────────────────────────────
    # Endereço para retirada
    # ─────────────────────────────────────────────

    pickup_address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Endereço para retirada",
        help_text=(
            "Endereço exibido ao cliente quando ele "
            "escolher retirar o pedido."
        )
    )

    pickup_number = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Número",
    )

    pickup_complement = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Complemento",
    )

    pickup_neighborhood = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Bairro",
    )

    pickup_city = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Cidade",
    )

    pickup_zip_code = models.CharField(
        max_length=9,
        blank=True,
        verbose_name="CEP",
    )

    fulfillment_mode = models.CharField(
        max_length=20,
        choices=FulfillmentMode.choices,
        default=FulfillmentMode.DELIVERY_AND_PICKUP,
        verbose_name="Modo de atendimento",
        help_text=(
            "Define se a loja oferece entrega e retirada, "
            "ou apenas retirada no local."
        )
    )

    @property
    def is_pickup_only(self):
        return self.fulfillment_mode == FulfillmentMode.PICKUP_ONLY

    @property
    def is_delivery_only(self):
        return self.fulfillment_mode == FulfillmentMode.DELIVERY_ONLY

    @property
    def accepts_delivery(self):
        return self.fulfillment_mode in (
            FulfillmentMode.DELIVERY_AND_PICKUP,
            FulfillmentMode.DELIVERY_ONLY,
        )

    @property
    def accepts_pickup(self):
        return self.fulfillment_mode in (
            FulfillmentMode.DELIVERY_AND_PICKUP,
            FulfillmentMode.PICKUP_ONLY,
        )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.whatsapp_number = re.sub(r"\D", "", self.whatsapp_number)

        is_new = self.pk is None

        super().save(*args, **kwargs)

        # Cria os 7 dias automaticamente ao criar a loja.
        if is_new:
            BusinessHour.objects.bulk_create([
                BusinessHour(
                    tenant=self,
                    weekday=weekday,
                    is_closed=True,
                    opening_time=None,
                    closing_time=None,
                )
                for weekday in range(7)
            ])

    def is_open_now(self):
        """
        Retorna True se a loja estiver aberta neste momento.

        Também considera horários que atravessam a meia-noite.

        Exemplo:
            Segunda: 18:00 -> 01:00

        Nesse caso:
            Segunda 20:00 = aberta
            Terça 00:30 = aberta
            Terça 02:00 = fechada
        """

        now = timezone.localtime()
        current_weekday = now.weekday()
        current_time = now.time()

        # ─────────────────────────────────────────
        # 1. Verifica o horário do dia atual
        # ─────────────────────────────────────────

        today_hours = self.business_hours.filter(
            weekday=current_weekday
        ).first()

        if today_hours and not today_hours.is_closed:
            if (
                today_hours.opening_time
                and today_hours.closing_time
            ):
                opening = today_hours.opening_time
                closing = today_hours.closing_time

                # Horário normal:
                # 08:00 -> 18:00
                if opening < closing:
                    if opening <= current_time < closing:
                        return True

                # Horário atravessando meia-noite:
                # 18:00 -> 01:00
                else:
                    if current_time >= opening:
                        return True

        # ─────────────────────────────────────────
        # 2. Verifica se estamos dentro de um horário
        #    iniciado no dia anterior.
        # ─────────────────────────────────────────

        previous_weekday = (current_weekday - 1) % 7

        previous_hours = self.business_hours.filter(
            weekday=previous_weekday
        ).first()

        if previous_hours and not previous_hours.is_closed:
            if (
                previous_hours.opening_time
                and previous_hours.closing_time
            ):
                opening = previous_hours.opening_time
                closing = previous_hours.closing_time

                # Só interessa aqui horário que atravessa
                # a meia-noite.
                if opening > closing:
                    if current_time < closing:
                        return True

        return False

    class Meta:
        verbose_name = "Loja"
        verbose_name_plural = "Lojas"
        ordering = ["name"]


class BusinessHour(models.Model):
    WEEKDAYS = [
        (0, "Segunda-feira"),
        (1, "Terça-feira"),
        (2, "Quarta-feira"),
        (3, "Quinta-feira"),
        (4, "Sexta-feira"),
        (5, "Sábado"),
        (6, "Domingo"),
    ]

    tenant = models.ForeignKey(
        "Tenant",
        on_delete=models.CASCADE,
        related_name="business_hours",
    )

    weekday = models.PositiveSmallIntegerField(
        choices=WEEKDAYS,
        verbose_name="Dia da semana",
    )

    is_closed = models.BooleanField(
        default=False,
        verbose_name="Fechado",
    )

    opening_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Abertura",
    )

    closing_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Fechamento",
    )

    class Meta:
        ordering = ["weekday", "opening_time"]

        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "weekday"],
                name="unique_business_hour_per_tenant_weekday",
            )
        ]

        verbose_name = "Horário de funcionamento"
        verbose_name_plural = "Horários de funcionamento"

    def __str__(self):
        day = dict(self.WEEKDAYS).get(
            self.weekday,
            ""
        )

        if self.is_closed:
            return f"{day} — Fechado"

        if self.opening_time and self.closing_time:
            return (
                f"{day} — "
                f"{self.opening_time:%H:%M} às "
                f"{self.closing_time:%H:%M}"
            )

        return day

    def clean(self):
        super().clean()

        # Se fechado, não precisa validar horários
        if self.is_closed:
            return

        if not self.opening_time or not self.closing_time:
            raise ValidationError(
                "Informe o horário de abertura e fechamento "
                "ou marque o dia como fechado."
            )

        # Horário normal: abertura deve ser antes do fechamento
        if self.opening_time < self.closing_time:
            return

        # Horário que atravessa a meia-noite é permitido
        if self.opening_time > self.closing_time:
            return

        # Se forem iguais, é inválido
        raise ValidationError(
            "O horário de abertura não pode ser igual ao de fechamento."
        )

    def save(self, *args, **kwargs):
        if self.is_closed:
            self.opening_time = None
            self.closing_time = None

        super().save(*args, **kwargs)


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

class DeliveryZone(models.Model):
    tenant = models.ForeignKey(
        'Tenant', on_delete=models.CASCADE, related_name='delivery_zones'
    )
    city = models.CharField(max_length=100, verbose_name="Cidade")
    neighborhood = models.CharField(max_length=100, verbose_name="Bairro")
    fee = models.DecimalField(
        max_digits=8, decimal_places=2, verbose_name="Taxa de entrega (R$)"
    )
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Zona de Entrega"
        verbose_name_plural = "Zonas de Entrega"

        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "city", "neighborhood"],
                name="unique_delivery_zone_per_tenant",
            ),
        ]

        ordering = ["city", "neighborhood"]

    def __str__(self):
        return f"{self.city} / {self.neighborhood} — R$ {self.fee:.2f}"
