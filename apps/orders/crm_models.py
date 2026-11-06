import uuid
from django.db import models
from django.utils import timezone
from apps.core.models import TenantModel


class LoyaltySettings(TenantModel):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE)
    enabled = models.BooleanField(default=False)
    enabled_at = models.DateTimeField(default=timezone.now)
    reais_per_point = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    reward_points = models.PositiveIntegerField(default=100)
    reward_value = models.DecimalField(max_digits=8, decimal_places=2, default=10)


class LoyaltyEntry(TenantModel):
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    order = models.OneToOneField(
        "orders.Order", on_delete=models.PROTECT, null=True, blank=True
    )
    campaign = models.OneToOneField(
        "coupons.CouponCampaign", on_delete=models.PROTECT, null=True, blank=True
    )
    key = models.CharField(max_length=120)
    points = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="loyalty_entry_key")
        ]


class CustomerProfile(TenantModel):
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE)
    birthday = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=1000, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer"], name="crm_customer_tenant"
            )
        ]


class CustomerCampaign(TenantModel):
    name = models.CharField(max_length=120)
    segment = models.CharField(max_length=30)
    text = models.CharField(max_length=1000)
    active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class FunnelEvent(TenantModel):
    session = models.CharField(max_length=64)
    stage = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "session", "stage"], name="funnel_session_stage"
            )
        ]
