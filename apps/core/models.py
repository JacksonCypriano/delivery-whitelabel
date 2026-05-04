from django.db import models

class TenantModel(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE)

    class Meta:
        abstract = True
