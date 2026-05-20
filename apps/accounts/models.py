from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError

from apps.tenants.models import Tenant


class User(AbstractUser):
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.CASCADE)
    is_tenant_admin = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.is_superuser and self.tenant_id:
            raise ValidationError("Superuser não pode ter tenant")

        if not self.is_superuser and not self.tenant_id:
            raise ValidationError("User comum precisa de tenant")

        return super().save(*args, **kwargs)
