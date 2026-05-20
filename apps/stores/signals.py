from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import HalfProduct, Product


@receiver(post_save, sender=Product)
def create_half_for_pizza(sender, instance, created, **kwargs):
    if instance.category and instance.category.name.lower() == 'pizzas':
        HalfProduct.objects.get_or_create(product=instance)
