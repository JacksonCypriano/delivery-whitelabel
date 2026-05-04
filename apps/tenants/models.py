from django.db import models

class Tenant(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    whatsapp_instance_key = models.CharField(max_length=255, blank=True, null=True)
    whatsapp_api_key = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class BrandConfig(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='brand_config')
    primary_color = models.CharField(max_length=7, default="#e74c3c")
    secondary_color = models.CharField(max_length=7, default="#2c3e50")
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    custom_domain = models.CharField(max_length=255, blank=True, null=True, unique=True)

    def __str__(self):
        return f"Config de Branding - {self.tenant.name}"