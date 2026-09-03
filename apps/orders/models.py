# apps/orders/models.py

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TenantModel
from apps.stores.models import Product
from apps.tenants.models import Tenant

from .choices import Status


User = settings.AUTH_USER_MODEL


class Cart(TenantModel):
    checkout_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="carts")
    session_key = models.CharField(max_length=128, null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Carrinho"
        verbose_name_plural = "Carrinhos"
        constraints = [
            models.CheckConstraint(
                check=models.Q(user__isnull=False, session_key__isnull=True) | models.Q(user__isnull=True, session_key__isnull=False),
                name="cart_user_or_session_exclusive",
            ),
            models.UniqueConstraint(fields=["tenant", "user"], condition=Q(user__isnull=False), name="unique_cart_tenant_user"),
            models.UniqueConstraint(fields=["tenant", "session_key"], condition=Q(user__isnull=True), name="unique_cart_tenant_session"),
        ]

    def __str__(self):
        if self.user:
            return f"Carrinho de {self.user.username}"

        return f"Carrinho anônimo ({self.session_key[:10]}...)"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    product_key = models.CharField(max_length=100, null=True, blank=True)
    name = models.CharField(max_length=200, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    combination_details = models.JSONField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True, help_text="Observações do cliente para o item")

    def get_total_price(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.name}"

    class Meta:
        verbose_name = "Item do carrinho"
        verbose_name_plural = "Itens do carrinho"
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product_key"],
                name="unique_cart_product_key",
                condition=Q(product_key__isnull=False),
            ),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="cart_item_quantity_positive"),
            models.CheckConstraint(condition=Q(price__gte=0), name="cart_item_price_nonnegative"),
        ]


class Order(TenantModel):
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Cliente",
    )

    customer_name = models.CharField(max_length=150, blank=True, verbose_name="Nome do cliente")
    customer_phone = models.CharField(max_length=20, verbose_name="Telefone do cliente")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="Situação")

    total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Subtotal")
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Taxa de entrega")

    coupon_code = models.CharField(max_length=40, blank=True, default="", verbose_name="Cupom utilizado")
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Desconto")

    # Snapshot do endereço usado no pedido
    delivery_zip_code = models.CharField(max_length=9, blank=True, verbose_name="CEP de entrega")
    delivery_street = models.CharField(max_length=255, blank=True, verbose_name="Rua / Avenida")
    delivery_number = models.CharField(max_length=20, blank=True, verbose_name="Número")
    delivery_complement = models.CharField(max_length=100, blank=True, verbose_name="Complemento")
    delivery_neighborhood = models.CharField(max_length=100, blank=True, verbose_name="Bairro")
    delivery_city = models.CharField(max_length=100, blank=True, verbose_name="Cidade")
    delivery_state = models.CharField(max_length=2, blank=True, verbose_name="Estado")
    delivery_reference = models.CharField(max_length=255, blank=True, verbose_name="Ponto de referência")

    delivery_type = models.CharField(
        max_length=20,
        choices=(
            ("delivery", "Entrega"),
            ("pickup", "Retirada"),
        ),
        default="delivery",
        verbose_name="Forma de recebimento",
    )

    payment_method = models.CharField(max_length=30, blank=True, default="", verbose_name="Forma de pagamento")
    payment_change_for = models.CharField(max_length=30, blank=True, default="", verbose_name="Troco para")

    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    checkout_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    source_cart_id = models.PositiveBigIntegerField(null=True, blank=True, editable=False)

    whatsapp_opened_at = models.DateTimeField(null=True, blank=True, verbose_name="WhatsApp aberto em")
    abandoned_at = models.DateTimeField(null=True, blank=True, verbose_name="Descartado em")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data do pedido")

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"

    def __str__(self):
        return f"Pedido #{self.id} - {self.customer_name or self.customer_phone}"

    @property
    def whatsapp_opened(self):
        return self.whatsapp_opened_at is not None

    @property
    def is_abandoned(self):
        return self.abandoned_at is not None

    @property
    def payment_label(self):
        labels = {
            "cash": "Dinheiro",
            "credit_card": "Cartão de Crédito",
            "debit_card": "Cartão de Débito",
            "pix": "PIX",
        }

        label = labels.get(self.payment_method, self.payment_method or "-")

        if self.payment_method == "cash" and self.payment_change_for:
            return f"{label} — troco para R$ {self.payment_change_for}"

        return label

    @property
    def delivery_type_label(self):
        if self.delivery_type == "pickup":
            return "Retirada"

        return "Entrega"

    @property
    def delivery_address_label(self):
        if self.delivery_type == "pickup":
            return "Retirada na loja"

        first_line = ", ".join(part for part in (self.delivery_street, self.delivery_number, self.delivery_complement) if part)

        city_state = self.delivery_city or ""

        if self.delivery_state:
            city_state += f"/{self.delivery_state}"

        second_line = " - ".join(part for part in (self.delivery_neighborhood, city_state) if part)

        parts = [part for part in (first_line, second_line) if part]

        if self.delivery_zip_code:
            parts.append(f"CEP {self.delivery_zip_code}")

        return " · ".join(parts)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE, verbose_name="Pedido")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Produto")

    name = models.CharField("Nome", max_length=255, blank=True)
    price = models.DecimalField("Preço", max_digits=10, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField("Quantidade")

    combination_details = models.JSONField(null=True, blank=True)
    product_key = models.CharField(max_length=100, blank=True, default="")
    notes = models.TextField("Observações", blank=True, default="", help_text="Observações do cliente no momento do pedido")

    class Meta:
        verbose_name = "Item do pedido"
        verbose_name_plural = "Itens do pedido"

    def get_total_price(self):
        return self.price * self.quantity

    def _customizations(self):
        combo = self.combination_details or {}

        if combo.get("product_ids"):
            return (
                list(combo.get("customizations_whole") or [])
                + list(combo.get("customizations_half1") or [])
                + list(combo.get("customizations_half2") or [])
            )

        return list(combo.get("customizations") or [])

    @property
    def additions_unit_price(self):
        total = Decimal("0.00")

        for item in self._customizations():
            try:
                total += Decimal(str(item.get("price", 0) or 0))
            except (TypeError, ValueError):
                continue

        return total.quantize(Decimal("0.01"))

    @property
    def base_unit_price(self):
        base = self.price - self.additions_unit_price

        if base < Decimal("0.00"):
            return self.price

        return base

    @property
    def has_additions(self):
        return self.additions_unit_price > Decimal("0.00")


class ProductCombination(models.Model):
    """Modelo para combinar produtos (ex: meio a meio de pizzas)"""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    combination_type = models.CharField(
        max_length=20,
        choices=[
            ("half_half", "Meio a Meio"),
            ("third_third", "Três Sabores"),
        ],
    )

    base_products = models.ManyToManyField(Product, related_name="combination_bases", limit_choices_to={"tenant": models.F("tenant")})

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_combination_type_display()})"

    class Meta:
        verbose_name = "Combinação de produtos"
        verbose_name_plural = "Combinações de produtos"


class CombinationPricingRule(models.Model):
    """Regras de precificação para combinações"""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    combination_type = models.CharField(max_length=20, choices=[("half_half", "Meio a Meio")])

    price_calculation_method = models.CharField(
        max_length=20,
        choices=[
            ("max_price", "Preço da Mais Cara"),
            ("average", "Média dos Preços"),
            ("sum_halved", "Soma/2"),
        ],
        default="max_price",
    )

    class Meta:
        verbose_name = "Regra de preço da combinação"
        verbose_name_plural = "Regras de preço das combinações"
        unique_together = ["tenant", "combination_type"]


class StockReservation(models.Model):
    """Demand snapshot; active only while the parent review is valid.

    Deducted quantities survive cancellation for idempotent stock returns.
    Existing orders have no rows, so historical sends are never debited again.
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='stock_reservations')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=150)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    deducted_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    returned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Reserva de estoque"
        verbose_name_plural = "Reservas de estoque"
        constraints = [
            models.UniqueConstraint(fields=['order', 'product'], name='unique_stock_order_product'),
            models.CheckConstraint(condition=Q(quantity__gt=0), name='stock_reserved_positive'),
            models.CheckConstraint(condition=Q(deducted_quantity__gte=0), name='stock_deducted_nonnegative'),
        ]
