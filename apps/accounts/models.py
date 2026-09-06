import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.tenants.models import Tenant


class User(AbstractUser):
    email_verified = models.BooleanField("E-mail verificado", default=False)
    email_verified_at = models.DateTimeField("E-mail verificado em", null=True, blank=True)

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

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

    must_change_password = models.BooleanField(
        default=False,
        verbose_name="Troca de senha obrigatória",
        help_text="Quando ativo, o lojista precisa definir uma nova senha antes de usar o painel.",
    )

    welcome_email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="E-mail de boas-vindas enviado em",
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


class PendingContactChange(models.Model):
    """One independently confirmable contact change per customer and channel."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pending_contact_changes")
    channel = models.CharField(max_length=8, choices=[("email", "E-mail"), ("whatsapp", "WhatsApp")])
    destination = models.CharField(max_length=150)
    original_value = models.CharField(max_length=150)
    expires_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    code_hash = models.CharField(max_length=128, blank=True)
    code_expires_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "channel"], name="unique_pending_contact_channel"),
        ]

    @property
    def masked_destination(self):
        if self.channel == "email":
            return self.destination[:1] + "***@" + self.destination.split("@")[-1]
        return "(**) *****-" + self.destination[-4:]


class SecurityEvent(models.Model):
    class Event(models.TextChoices):
        LOGIN_SUCCEEDED = "login_succeeded", "Login concluído"
        LOGIN_FAILED = "login_failed", "Falha no login"
        LOGOUT = "logout", "Saída da conta"
        ACCESS_DENIED = "access_denied", "Acesso recusado"
        RATE_LIMITED = "rate_limited", "Limite de tentativas atingido"
        REGISTRATION_STARTED = "registration_started", "Cadastro iniciado"
        ACCOUNT_CREATED = "account_created", "Conta criada"
        OTP_SENT = "otp_sent", "OTP aceito pelo provedor"
        OTP_CONFIRMED = "otp_confirmed", "OTP confirmado"
        OTP_REJECTED = "otp_rejected", "OTP recusado"
        OTP_DELIVERY_FAILED = "otp_delivery_failed", "Falha no envio do OTP"
        CONTACT_REQUESTED = "contact_requested", "Alteração de contato solicitada"
        CONTACT_CANCELLED = "contact_cancelled", "Alteração de contato cancelada"
        EMAIL_CHANGED = "email_changed", "E-mail alterado"
        PHONE_CHANGED = "phone_changed", "WhatsApp alterado"
        PASSWORD_CHANGED = "password_changed", "Senha alterada"
        PASSWORD_RESET_REQUESTED = "password_reset_requested", "Recuperação de senha solicitada"
        PASSWORD_RESET_FAILED = "password_reset_failed", "Falha na recuperação de senha"
        TOKEN_REFRESHED = "token_refreshed", "Token de acesso renovado"

    class Reason(models.TextChoices):
        NONE = "", "—"
        INVALID_CREDENTIALS = "invalid_credentials", "Credenciais inválidas"
        INVALID_INPUT = "invalid_input", "Dados inválidos"
        NOT_ALLOWED = "not_allowed", "Operação não permitida"
        RATE_LIMIT = "rate_limit", "Limite de envios ou tentativas"
        COOLDOWN = "cooldown", "Intervalo entre envios"
        ATTEMPTS = "attempts", "Tentativas de OTP esgotadas"
        EXPIRED = "expired", "Código ou solicitação expirado"
        DELIVERY = "delivery", "Provedor indisponível ou envio não confirmado"
        INVALID_CODE = "invalid_code", "Código incorreto"
        REJECTED = "rejected", "Solicitação inválida ou já encerrada"
        UNEXPECTED = "unexpected", "Erro interno"

    created_at = models.DateTimeField(default=timezone.now, db_index=True, editable=False, verbose_name="Data e hora")
    event = models.CharField(max_length=32, choices=Event.choices, db_index=True, verbose_name="Evento")
    scope = models.CharField(max_length=20, choices=[("auth", "Autenticação"), ("account", "Conta"), ("registration", "Cadastro"), ("contact", "Contato"), ("dashboard", "API do lojista")], verbose_name="Fluxo")
    reason = models.CharField(max_length=24, choices=Reason.choices, blank=True, verbose_name="Motivo")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="security_events", verbose_name="Conta afetada")
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="performed_security_events", verbose_name="Usuário da sessão")
    channel = models.CharField(max_length=8, choices=[("email", "E-mail"), ("whatsapp", "WhatsApp")], blank=True, verbose_name="Canal")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP")
    request_id = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="ID da requisição")
    route = models.CharField(max_length=120, blank=True, verbose_name="Rota (sem parâmetros)")
    reference = models.UUIDField(null=True, blank=True, db_index=True, verbose_name="ID da solicitação OTP")
    identifier_hash = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="Identificador protegido")

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Evento de segurança"
        verbose_name_plural = "Eventos de segurança"
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.get_event_display()} — {self.created_at:%d/%m/%Y %H:%M}"
