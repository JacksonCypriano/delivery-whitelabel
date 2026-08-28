from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

from apps.tenants.models import Tenant


class User(AbstractUser):
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
