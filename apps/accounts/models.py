import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

from apps.tenants.models import Tenant


class User(AbstractUser):
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    tenant = models.ForeignKey(
        Tenant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="users",
        verbose_name="Loja",
    )

    is_tenant_admin = models.BooleanField(
        default=False,
        verbose_name="Administrador da loja",
    )

    def clean(self):
        super().clean()

        # Superusuário é global e nunca pertence a uma loja.
        if self.is_superuser and self.tenant_id:
            raise ValidationError(
                "Superusuário não pode estar vinculado a uma loja."
            )

        # Administrador de loja obrigatoriamente pertence a um tenant.
        if self.is_tenant_admin and not self.tenant_id:
            raise ValidationError(
                "Administrador de loja precisa estar vinculado a uma loja."
            )

        # Consumidores são globais:
        #
        # tenant = None
        # is_tenant_admin = False
        #
        # Isso é permitido.

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class PendingRegistration(models.Model):
    """Session-bound registration. Never stores passwords or OTPs in plaintext."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=150)
    phone = models.CharField(max_length=20)
    password_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField(db_index=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    code_hash = models.CharField(max_length=128, blank=True)
    code_expires_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    @property
    def channel(self):
        return "whatsapp" if self.email_verified_at else "email"


class RegistrationRateLimit(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    events = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
