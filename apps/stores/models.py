from django.db import models

from apps.core.models import TenantModel


class Category(TenantModel):
    name = models.CharField(max_length=100)

class Product(TenantModel):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)
