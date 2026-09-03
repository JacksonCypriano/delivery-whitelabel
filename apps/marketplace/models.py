from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from apps.tenants.models import Tenant


class MarketplaceCategory(models.Model):
    name = models.CharField(max_length=80, unique=True, verbose_name="Nome")
    slug = models.SlugField("Identificador na URL", max_length=90, unique=True, blank=True)
    icon = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="Ícone",
        help_text="Emoji opcional, ex.: 🍕",
    )
    is_active = models.BooleanField(default=True, verbose_name="Ativa")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordem")

    class Meta:
        verbose_name = "Categoria do marketplace"
        verbose_name_plural = "Categorias do marketplace"
        ordering = ("order", "name")
        indexes = [
            models.Index(fields=["is_active", "order"]),
            models.Index(fields=["slug"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:90]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class MarketplaceProfile(models.Model):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="marketplace_profile",
        verbose_name="Loja",
    )

    is_listed = models.BooleanField(
        default=True,
        verbose_name="Exibir no marketplace",
        help_text="Quando desmarcado, a loja continua funcionando no subdomínio, mas não aparece na vitrine geral.",
    )
    is_featured = models.BooleanField(
        default=False,
        verbose_name="Loja em destaque",
        help_text="Use para priorizar uma loja na vitrine.",
    )
    priority = models.PositiveIntegerField(
        default=0,
        verbose_name="Prioridade",
        help_text="Quanto maior, mais acima a loja aparece entre lojas equivalentes.",
    )

    short_description = models.CharField(
        max_length=180,
        blank=True,
        verbose_name="Descrição curta",
        help_text="Texto compacto exibido no card da loja.",
    )
    search_keywords = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Palavras-chave",
        help_text="Termos adicionais separados por vírgula. Ex.: artesanal, rodízio, lanche, japonesa.",
    )

    categories = models.ManyToManyField(
        MarketplaceCategory,
        blank=True,
        related_name="stores",
        verbose_name="Categorias",
    )

    city = models.CharField(max_length=100, blank=True, db_index=True, verbose_name="Cidade")
    state = models.CharField(max_length=2, blank=True, db_index=True, verbose_name="UF")
    neighborhood = models.CharField(max_length=100, blank=True, db_index=True, verbose_name="Bairro")

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Latitude",
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Longitude",
    )
    service_radius_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Raio de atendimento (km)",
        help_text="Opcional. Preparado para busca por proximidade no futuro.",
    )

    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Perfil no marketplace"
        verbose_name_plural = "Perfis no marketplace"
        ordering = ("-is_featured", "-priority", "tenant__name")
        indexes = [
            models.Index(fields=["is_listed", "is_featured"]),
            models.Index(fields=["city", "state"]),
            models.Index(fields=["neighborhood"]),
        ]

    def clean(self):
        super().clean()

        if self.state:
            self.state = self.state.strip().upper()

        if self.latitude is not None and not (Decimal("-90") <= self.latitude <= Decimal("90")):
            raise ValidationError({"latitude": "Latitude deve estar entre -90 e 90."})

        if self.longitude is not None and not (Decimal("-180") <= self.longitude <= Decimal("180")):
            raise ValidationError({"longitude": "Longitude deve estar entre -180 e 180."})

        if self.service_radius_km is not None and self.service_radius_km < 0:
            raise ValidationError({"service_radius_km": "O raio não pode ser negativo."})

    def save(self, *args, **kwargs):
        if self.state:
            self.state = self.state.strip().upper()

        if self.city:
            self.city = self.city.strip()

        if self.neighborhood:
            self.neighborhood = self.neighborhood.strip()

        if self.search_keywords:
            self.search_keywords = ", ".join(
                part.strip()
                for part in self.search_keywords.split(",")
                if part.strip()
            )

        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def location_label(self):
        parts = [part for part in (self.neighborhood, self.city) if part]
        label = " • ".join(parts)
        if self.state:
            label = f"{label}/{self.state}" if label else self.state
        return label

    def __str__(self):
        return f"Marketplace - {self.tenant.name}"



class MarketplaceFavoriteStore(models.Model):
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="favorite_marketplace_stores",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="marketplace_favorites",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Loja favorita"
        verbose_name_plural = "Lojas favoritas"
        constraints = [
            models.UniqueConstraint(
                fields=("customer", "tenant"),
                name="unique_marketplace_favorite_store",
            ),
        ]
        indexes = [
            models.Index(
                fields=("customer", "created_at"),
            ),
        ]

    def __str__(self):
        return (
            f"{self.customer} ♥ "
            f"{self.tenant.name}"
        )
