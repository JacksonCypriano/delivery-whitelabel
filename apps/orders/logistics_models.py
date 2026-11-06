from django.db import models
from django.conf import settings
from apps.core.models import TenantModel


class Courier(TenantModel):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=24)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class DeliveryAssignment(TenantModel):
    order = models.OneToOneField(
        "orders.Order", on_delete=models.PROTECT, related_name="delivery_assignment"
    )
    courier = models.ForeignKey(Courier, on_delete=models.PROTECT)
    assigned_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    recipient = models.CharField(max_length=80, blank=True)
    latitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    photo = models.BinaryField(null=True, blank=True)


class DeliveryAudit(TenantModel):
    assignment = models.ForeignKey(
        DeliveryAssignment, on_delete=models.PROTECT, related_name="events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    action = models.CharField(max_length=24)
    courier_name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
