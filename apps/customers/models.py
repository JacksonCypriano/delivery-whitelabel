from django.conf import settings
from django.db import models

# Create your views here.

class Customer(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile", verbose_name="Usuário")
    phone = models.CharField(max_length=20, unique=True, verbose_name="Telefone")
    phone_verified = models.BooleanField(default=False, verbose_name="Telefone verificado")
    phone_verified_at = models.DateTimeField(null=True, blank=True, verbose_name="Data da verificação do telefone")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data de cadastro")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última atualização")

    def __str__(self):
        return (self.user.get_full_name() or self.user.username)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"


class CustomerAddress(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses", verbose_name="Cliente")
    label = models.CharField(max_length=50, default="Casa", verbose_name="Identificação", help_text="Ex.: Casa, Trabalho, Apartamento")
    zip_code = models.CharField(max_length=9, verbose_name="CEP")
    street = models.CharField(max_length=255, verbose_name="Rua / Avenida")
    number = models.CharField(max_length=20, verbose_name="Número")
    complement = models.CharField(max_length=100, blank=True, verbose_name="Complemento")
    neighborhood = models.CharField(max_length=100, verbose_name="Bairro")
    city = models.CharField(max_length=100, verbose_name="Cidade")
    state = models.CharField(max_length=2, verbose_name="Estado")
    reference = models.CharField(max_length=255, blank=True, verbose_name="Ponto de referência")
    is_default = models.BooleanField(default=False, verbose_name="Endereço principal")
    created_at = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Endereço"
        verbose_name_plural = "Endereços"

    def save(self, *args, **kwargs):
        if self.is_default:
            CustomerAddress.objects.filter(
                customer=self.customer,
                is_default=True,
            ).exclude(pk=self.pk).update(
                is_default=False
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.label} - "
            f"{self.street}, {self.number} - "
            f"{self.neighborhood}"
        )
