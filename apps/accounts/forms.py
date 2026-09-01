from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.customers.models import Customer
from apps.integrations.whatsapp.service import get_whatsapp_service, normalize_br_phone

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
        max_length=150,
        label="E-mail",
    )

    phone = forms.CharField(
        max_length=20,
        label="WhatsApp / Telefone",
    )

    def __init__(self, *args, user=None, customer=None, skip_whatsapp_validation=False, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.customer = customer
        self.skip_whatsapp_validation = skip_whatsapp_validation

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
        raw_phone = self.cleaned_data["phone"]
        try:
            phone = normalize_br_phone(raw_phone)[2:]
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        queryset = Customer.objects.filter(phone=phone)
        if self.customer:
            queryset = queryset.exclude(pk=self.customer.pk)
        if queryset.exists():
            raise ValidationError("Já existe uma conta cadastrada com este telefone.")

        phone_changed = not self.customer or self.customer.phone != phone
        self.whatsapp_check = None
        if phone_changed and not self.skip_whatsapp_validation:
            self.whatsapp_check = get_whatsapp_service().check_number(phone)
            if self.whatsapp_check.available and self.whatsapp_check.exists is False:
                raise ValidationError("Este número não foi encontrado no WhatsApp. Verifique o DDD e o telefone informado.")
        return phone

    def save(self):
        from .contact_otp import save_profile

        self.user, self.pending_changes = save_profile(self.user.pk, self.cleaned_data)
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
        max_length=150,
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
        raw_phone = self.cleaned_data["phone"]
        try:
            phone = normalize_br_phone(raw_phone)[2:]
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        if Customer.objects.filter(phone=phone).exists():
            raise ValidationError("Já existe uma conta cadastrada com este telefone.")

        self.whatsapp_check = get_whatsapp_service().check_number(phone)
        if self.whatsapp_check.available and self.whatsapp_check.exists is False:
            raise ValidationError("Este número não foi encontrado no WhatsApp. Verifique o DDD e o telefone informado.")
        return phone

    def clean(self):
        cleaned_data = super().clean()

        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "As senhas não coincidem.")

        if password1:
            try:
                validate_password(password1)
            except ValidationError as exc:
                self.add_error("password1", exc)

        return cleaned_data

    def save(self):
        from .otp import create_pending
        return create_pending(self.cleaned_data)


class CustomerPasswordResetForm(PasswordResetForm):
    """Password recovery restricted to global consumer accounts."""

    def get_users(self, email):
        users = User._default_manager.filter(
            email__iexact=email,
            is_active=True,
            tenant__isnull=True,
            is_tenant_admin=False,
            is_staff=False,
            is_superuser=False,
            customer_profile__isnull=False,
        )

        return (
            user
            for user in users
            if user.has_usable_password()
        )


class CustomerLoginForm(forms.Form):
    email = forms.EmailField(
        label="E-mail",
    )

    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput,
    )

    def __init__(self, *args, request=None, authentication_blocked=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.authentication_blocked = authentication_blocked
        self.user = None

    def clean(self):
        cleaned_data = super().clean()
        if self.authentication_blocked:
            raise ValidationError("Muitas tentativas. Aguarde alguns minutos e tente novamente.")

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
