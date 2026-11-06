"""Sales automation records; all recipients and settings are tenant scoped."""

import uuid
from django.db import models
from django.db.models import Q
from apps.core.models import TenantModel


class SalesSettings(TenantModel):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE)
    scheduling_enabled = models.BooleanField(default=False)
    lead_minutes = models.PositiveIntegerField(default=60)
    horizon_days = models.PositiveIntegerField(default=7)
    recovery_enabled = models.BooleanField(default=False)
    recovery_minutes = models.PositiveIntegerField(default=60)
    feedback_enabled = models.BooleanField(default=False)
    feedback_minutes = models.PositiveIntegerField(default=120)
    reactivation_enabled = models.BooleanField(default=False)
    inactive_days = models.PositiveIntegerField(default=30)


class MarketingConsent(TenantModel):
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE)
    allowed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer"], name="sales_consent_customer"
            )
        ]


class SalesMessage(TenantModel):
    campaign = models.ForeignKey(
        "orders.CustomerCampaign", null=True, blank=True, on_delete=models.SET_NULL
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE)
    kind = models.CharField(max_length=24)
    key = models.CharField(max_length=120)
    cart = models.ForeignKey(
        "orders.Cart", null=True, blank=True, on_delete=models.SET_NULL
    )
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL
    )
    text = models.TextField(blank=True)
    recipient = models.CharField(max_length=24, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    attempted_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    skipped_at = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="sales_message_once")
        ]


class OrderFeedback(TenantModel):
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    handled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5), name="feedback_rating_1_5"
            )
        ]
