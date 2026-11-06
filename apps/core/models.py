import uuid
from django.db import models


class TenantModel(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)

    class Meta:
        abstract = True


class AdminSelection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey("accounts.User", on_delete=models.CASCADE)
    tenant = models.ForeignKey("tenants.Tenant", null=True, on_delete=models.CASCADE)
    scope = models.CharField(max_length=20)
    resource = models.CharField(max_length=100)
    query = models.TextField()
    count = models.PositiveIntegerField()
    fingerprint = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)


class AdminSelectionItem(models.Model):
    selection = models.ForeignKey(
        AdminSelection, on_delete=models.CASCADE, related_name="items"
    )
    object_pk = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["selection", "object_pk"], name="admin_selection_unique_object"
            )
        ]


class AdminActivityScope(models.Model):
    entry = models.OneToOneField(
        "admin.LogEntry", on_delete=models.CASCADE, related_name="react_scope"
    )
    tenant = models.ForeignKey("tenants.Tenant", null=True, on_delete=models.CASCADE)
