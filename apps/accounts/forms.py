from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.customers.models import Customer

User = get_user_model()


class CustomerProfileForm(forms.Form):
    first_name = forms.CharField(
        max_length=150,
        label="Nome",
    )

    last_name = forms.CharField(
        max_length=150,
        label="Sobrenome",
    )

    email = forms.EmailField(
        label="E-mail",
    )

    phone = forms.CharField(
        max_length=20,
        label="WhatsApp / Telefone",
    )

    def __init__(self, *args, user=None, customer=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.customer = customer

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        queryset = User.objects.filter(
            Q(email__iexact=email)
            | Q(username__iexact=email)
        )

        if self.user:
            queryset = queryset.exclude(pk=self.user.pk)

        if queryset.exists():
            raise ValidationError(
                "Já existe uma conta cadastrada com este e-mail."
            )

        return email

    def clean_phone(self):
        phone = self.cleaned_data["phone"]

        phone = "".join(
            char for char in phone
            if char.isdigit()
        )

        if phone.startswith("55") and len(phone) in (12, 13):
            phone = phone[2:]

        if len(phone) not in (10, 11):
            raise ValidationError(
                "Informe um telefone válido com DDD."
            )

        queryset = Customer.objects.filter(
            phone=phone
        )

        if self.customer:
            queryset = queryset.exclude(pk=self.customer.pk)

        if queryset.exists():
            raise ValidationError(
                "Já existe uma conta cadastrada com este telefone."
            )

        return phone

    def save(self):
        email = self.cleaned_data["email"]

        self.user.first_name = self.cleaned_data["first_name"]
        self.user.last_name = self.cleaned_data["last_name"]
        self.user.email = email

        # Consumidores usam e-mail como username.
        self.user.username = email

        self.user.save(
            update_fields=[
                "first_name",
                "last_name",
                "email",
                "username",
            ]
        )

        self.customer.phone = self.cleaned_data["phone"]

        self.customer.save(
            update_fields=[
                "phone",
                "updated_at",
            ]
        )

        return self.user


class CustomerPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        label="Senha atual",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Digite sua senha atual",
            }
        ),
    )

    new_password1 = forms.CharField(
        label="Nova senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Digite a nova senha",
            }
        ),
    )

    new_password2 = forms.CharField(
        label="Confirmar nova senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Digite novamente a nova senha",
            }
        ),
    )


class CustomerRegisterForm(forms.Form):
    first_name = forms.CharField(
        max_length=150,
        label="Nome",
    )

    last_name = forms.CharField(
        max_length=150,
        label="Sobrenome",
    )

    email = forms.EmailField(
        label="E-mail",
    )

    phone = forms.CharField(
        max_length=20,
        label="WhatsApp / Telefone",
    )

    password1 = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput,
    )

    password2 = forms.CharField(
        label="Confirmar senha",
        widget=forms.PasswordInput,
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(
            Q(email__iexact=email)
            | Q(username__iexact=email)
        ).exists():
            raise ValidationError(
                "Já existe uma conta cadastrada com este e-mail."
            )

        return email

    def clean_phone(self):
        phone = self.cleaned_data["phone"]

        # Mantém somente números
        phone = "".join(
            char for char in phone
            if char.isdigit()
        )

        # Se vier com código do Brasil, remove o 55
        if phone.startswith("55") and len(phone) in (12, 13):
            phone = phone[2:]

        if len(phone) not in (10, 11):
            raise ValidationError(
                "Informe um telefone válido com DDD."
            )

        if Customer.objects.filter(phone=phone).exists():
            raise ValidationError(
                "Já existe uma conta cadastrada com este telefone."
            )

        return phone

    def clean(self):
        cleaned_data = super().clean()

        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error(
                "password2",
                "As senhas não coincidem.",
            )

        return cleaned_data

    def save(self):
        email = self.cleaned_data["email"]

        # Como seu AUTH_USER_MODEL ainda autentica por username,
        # usamos o e-mail também como username do consumidor.
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            password=self.cleaned_data["password1"],

            # Consumidor global
            tenant=None,
            is_tenant_admin=False,
            is_staff=False,
        )

        Customer.objects.create(
            user=user,
            phone=self.cleaned_data["phone"],
        )

        return user


class CustomerLoginForm(forms.Form):
    email = forms.EmailField(
        label="E-mail",
    )

    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput,
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None

    def clean(self):
        cleaned_data = super().clean()

        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if not email or not password:
            return cleaned_data

        self.user = authenticate(
            request=self.request,
            username=email.strip().lower(),
            password=password,
        )

        if not self.user:
            raise ValidationError(
                "E-mail ou senha inválidos."
            )

        if not hasattr(self.user, "customer_profile"):
            raise ValidationError(
                "Esta conta não é uma conta de consumidor."
            )

        if not self.user.is_active:
            raise ValidationError(
                "Esta conta está desativada."
            )

        return cleaned_data

    def get_user(self):
        return self.user
