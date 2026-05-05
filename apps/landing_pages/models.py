# apps/landing_pages/models.py
from django.db import models
from apps.tenants.models import Tenant

class LandingPage(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    hero_image = models.ImageField(upload_to='landings/heroes/', blank=True)
    cta_button_text = models.CharField(max_length=50, default="Peça Agora")
    cta_link = models.URLField(default="/menu")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} - {self.tenant.name}"

class ThemeTemplate(models.Model):
    name = models.CharField(max_length=100)
    primary_color = models.CharField(max_length=7)
    secondary_color = models.CharField(max_length=7)
    accent_color = models.CharField(max_length=7)
    background_color = models.CharField(max_length=7)
    text_color = models.CharField(max_length=7)

    def apply_to_tenant(self, tenant):
        brand, _ = tenant.brand_config.get_or_create(tenant=tenant)
        brand.primary_color = self.primary_color
        brand.secondary_color = self.secondary_color
        brand.accent_color = self.accent_color
        brand.background_color = self.background_color
        brand.text_color = self.text_color
        brand.save()

    def __str__(self):
        return self.name
