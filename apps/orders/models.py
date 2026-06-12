# apps/orders/models.py
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TenantModel
from apps.stores.models import Product
from apps.tenants.models import Tenant

from .choices import Status

User = settings.AUTH_USER_MODEL


class Cart(TenantModel):
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='carts'
    )
    session_key = models.CharField(
        max_length=128, 
        null=True, 
        blank=True,
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(user__isnull=False, session_key__isnull=True) |
                    models.Q(user__isnull=True, session_key__isnull=False)
                ),
                name='cart_user_or_session_exclusive'
            )
        ]

    def __str__(self):
        if self.user:
            return f"Carrinho de {self.user.username}"
        return f"Carrinho anônimo ({self.session_key[:10]}...)"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
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
        constraints = [
            models.UniqueConstraint(
                fields=['cart', 'product'],
                name='unique_cart_product',
                condition=Q(product__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['cart', 'product_key'],
                name='unique_cart_product_key',
                condition=Q(product_key__isnull=False)
            ),
        ]


class Order(TenantModel):
    customer_phone = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pedido {self.id} - {self.get_status_display()}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField()
    combination_details = models.JSONField(null=True, blank=True)

    def get_total_price(self):
        return self.product.price * self.quantity


class ProductCombination(models.Model):
    """Modelo para combinar produtos (ex: meio a meio de pizzas)"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    combination_type = models.CharField(
        max_length=20,
        choices=[
            ('half_half', 'Meio a Meio'),
            ('third_third', 'Três Sabores'),
        ]
    )
    base_products = models.ManyToManyField(
        Product, 
        related_name='combination_bases',
        limit_choices_to={'tenant': models.F('tenant')}
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_combination_type_display()})"


class CombinationPricingRule(models.Model):
    """Regras de precificação para combinações"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    combination_type = models.CharField(max_length=20, choices=[('half_half', 'Meio a Meio')])
    price_calculation_method = models.CharField(
        max_length=20,
        choices=[
            ('max_price', 'Preço da Mais Cara'),
            ('average', 'Média dos Preços'),
            ('sum_halved', 'Soma/2'),
        ],
        default='max_price'
    )
    
    class Meta:
        unique_together = ['tenant', 'combination_type']
