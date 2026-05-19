import uuid
from django.db import models
from apps.tenants.models import Tenant


class WhatsAppConfig(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="whatsapp_configs")
    is_active = models.BooleanField(default=True)
    display_phone_number = models.CharField(max_length=20)
    phone_number_id = models.CharField(max_length=64, unique=True)
    business_account_id = models.CharField(max_length=64)
    access_token = models.CharField(max_length=512)
    verify_token = models.CharField(max_length=128, default=uuid.uuid4, help_text="Token usado para validar o webhook da Meta.")
    app_secret = models.CharField(max_length=256, blank=True, default="", help_text="Opcional. Usado para validar assinatura HMAC do webhook.")
    webhook_subscribed = models.BooleanField(default=False, help_text="Indica se o webhook já foi registrado na Meta.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "WhatsApp Config"
        verbose_name_plural = "WhatsApp Configs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tenant} — {self.display_phone_number}"
