from django.db import models

class Status(models.TextChoices):
    PENDING = 'pending', 'Pendente'
    CONFIRMED = 'confirmed', 'Confirmado'
    DELIVERED = 'delivered', 'Entregue'
    CANCELLED = 'cancelled', 'Cancelado'
