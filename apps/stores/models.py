import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify

from apps.core.models import TenantModel

from .choices import ApplyToChoices

MIN_IMAGE_WIDTH = 500
MIN_IMAGE_HEIGHT = 500


def validate_image_resolution(image):
    if not image:
        return
    try:
        width, height = get_image_dimensions(image)
    except Exception:
        raise ValidationError("Não foi possível ler a imagem. Faça upload de um arquivo de imagem válido.")
    if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
        raise ValidationError(
            f"A imagem deve ter pelo menos {MIN_IMAGE_WIDTH}x{MIN_IMAGE_HEIGHT}px (atual: {width}x{height})."
        )


DAYS_OF_WEEK = [
    (0, 'Segunda-feira'),
    (1, 'Terça-feira'),
    (2, 'Quarta-feira'),
    (3, 'Quinta-feira'),
    (4, 'Sexta-feira'),
    (5, 'Sábado'),
    (6, 'Domingo'),
]


class Category(TenantModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'slug'],
                name='unique_category_slug_per_tenant'
            )
        ]
        indexes = [
            models.Index(fields=['tenant', 'slug']),
            models.Index(fields=['name']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)[:200]
            slug = base_slug
            n = 1
            while Category.objects.filter(slug=slug, tenant=self.tenant).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(TenantModel):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    sku = models.CharField(max_length=64, null=True, blank=True)
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_vegan = models.BooleanField(default=False)
    is_spicy = models.BooleanField(default=False)
    allergens = models.CharField(max_length=255, blank=True, help_text="Ex: glúten, leite, ovo")
    calories = models.PositiveIntegerField(null=True, blank=True, help_text="Calorias por porção")
    prep_time = models.PositiveIntegerField(null=True, blank=True, help_text="Tempo de preparo em minutos")
    weight = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, help_text="Peso em gramas")
    stock = models.IntegerField(null=True, blank=True, help_text="Quantidade em estoque (se aplicável)")
    min_order_qty = models.PositiveIntegerField(default=1)
    max_order_qty = models.PositiveIntegerField(null=True, blank=True)
    primary_image = models.ImageField(
        upload_to='products/%Y/%m/%d/',
        null=True,
        blank=True,
        validators=[validate_image_resolution]
    )
    available_days = models.JSONField(
        default=list,
        blank=True,
        help_text="Dias da semana em que o produto aparece no cardápio. Deixe vazio para aparecer todos os dias."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ['-is_featured', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'slug'],
                name='unique_product_slug_per_tenant'
            ),
            models.UniqueConstraint(
                fields=['tenant', 'sku'],
                name='unique_product_sku_per_tenant'
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'slug']),
            models.Index(fields=['name']),
        ]

    def clean(self):
        if self.price is not None and self.price < Decimal('0.00'):
            raise ValidationError({'price': "O preço deve ser igual ou maior que 0."})
        if self.sale_price and self.sale_price < Decimal('0.00'):
            raise ValidationError({'sale_price': "O preço promocional deve ser igual ou maior que 0."})
        if self.sale_price and self.sale_price > self.price:
            raise ValidationError({'sale_price': "O preço promocional não pode ser maior que o preço normal."})
        if self.stock is not None and self.stock < 0:
            raise ValidationError({'stock': "Estoque não pode ser negativo."})
        if self.max_order_qty and self.max_order_qty < self.min_order_qty:
            raise ValidationError({'max_order_qty': "Quantidade máxima não pode ser menor que a mínima."})
        if self.category and self.category.tenant_id != self.tenant_id:
            raise ValidationError({'category': "A categoria deve pertencer ao mesmo tenant do produto."})

    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.slug:
            base_slug = slugify(self.name)[:150]
            slug = base_slug
            n = 1
            while Product.objects.filter(slug=slug, tenant=self.tenant).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        if not self.sku:
            self.sku = f"P{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def get_primary_image(self):
        primary_img = getattr(self, 'images', None)
        if primary_img is not None:
            q = self.images.filter(is_primary=True).first()
            if q:
                return q.image.url if q.image else None
            first = self.images.first()
            if first:
                return first.image.url if first.image else None
        if self.primary_image:
            return self.primary_image.url
        return None

    def __str__(self):
        return self.name


class ProductImage(TenantModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(
        upload_to='products/images/%Y/%m/%d/',
        validators=[validate_image_resolution]
    )
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Imagem de produto"
        verbose_name_plural = "Imagens de produto"
        ordering = ['order']

    def save(self, *args, **kwargs):
        if self.product and not self.tenant_id:
            self.tenant_id = self.product.tenant_id
        super().save(*args, **kwargs)
        if self.is_primary:
            if self.product.primary_image != self.image:
                self.product.primary_image = self.image
                self.product.save(update_fields=['primary_image'])


class HalfProduct(TenantModel):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='half_variant')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sabor para meio a meio"
        verbose_name_plural = "Sabores para meio a meio"

    def __str__(self):
        return f"Meia {self.product.name}"

    def save(self, *args, **kwargs):
        if self.product and not self.tenant_id:
            self.tenant_id = self.product.tenant_id
        super().save(*args, **kwargs)


class CustomizationGroupLabel(TenantModel):
    """
    Rótulos reutilizáveis para grupos de personalização.
    Ex: 'Adicionais', 'Bordas', 'Molhos'.
    Crie uma vez e reutilize em qualquer grupo.
    """
    name = models.CharField(
        max_length=100,
        verbose_name="Nome",
        help_text="Ex: Adicionais, Bordas, Molhos"
    )

    class Meta:
        verbose_name = "Rótulo de Grupo de Personalização"
        verbose_name_plural = "Rótulos de Grupos de Personalização"
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='unique_label_name_per_tenant'
            )
        ]

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CustomizationGroup(TenantModel):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='customization_groups',
        verbose_name="Categoria"
    )
    label = models.ForeignKey(
        CustomizationGroupLabel,
        on_delete=models.SET_NULL,   # SET_NULL em vez de PROTECT (compatível com null=True)
        null=True,
        blank=True,
        related_name='groups',
        verbose_name="Nome do grupo",
        help_text="Selecione um rótulo existente ou crie um novo (ex: Adicionais, Bordas)"
    )
    apply_to = models.CharField(
        max_length=10,
        choices=ApplyToChoices.choices,
        default=ApplyToChoices.WHOLE,
        verbose_name="Aplicar a",
        help_text="Onde esse grupo aparecerá na modal"
    )
    min_options = models.PositiveIntegerField(
        default=0,
        verbose_name="Mínimo de opções",
        help_text="Mínimo de opções (0 para opcional)"
    )
    max_options = models.PositiveIntegerField(
        default=1,
        verbose_name="Máximo de opções",
        help_text="Máximo de opções permitidas"
    )
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Grupo de Personalização"
        verbose_name_plural = "Grupos de Personalização"
        ordering = ['label__name']

    @property
    def name(self):
        """Compatibilidade: acessa o nome via label."""
        return self.label.name if self.label_id else ""

    def __str__(self):
        label_name = self.label.name if self.label_id else "Sem rótulo"
        return f"{label_name} ({self.category.name})"


class CustomizationOption(TenantModel):
    group = models.ForeignKey(CustomizationGroup, on_delete=models.CASCADE, related_name='options')
    name = models.CharField(max_length=100, verbose_name="Nome")
    description = models.TextField(blank=True, verbose_name="Descrição")
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Preço"
    )
    image = models.ImageField(
        upload_to='customizations/%Y/%m/%d/',
        null=True,
        blank=True,
        validators=[validate_image_resolution],
        verbose_name="Imagem"
    )
    is_available = models.BooleanField(default=True, verbose_name="Disponível")

    class Meta:
        verbose_name = "Opção de Personalização"
        verbose_name_plural = "Opções de Personalização"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if self.group and not self.tenant_id:
            self.tenant_id = self.group.tenant_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} (+R$ {self.price})"


@receiver(post_save, sender=Product)
def create_half_product(sender, instance, created, **kwargs):
    if created:
        HalfProduct.objects.get_or_create(product=instance)
