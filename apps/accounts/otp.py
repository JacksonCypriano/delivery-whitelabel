"""Registration OTP state machine; database locks serialize sends and verification."""
import secrets
from datetime import timedelta
from urllib.parse import quote

import requests
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.debug import sensitive_variables

from apps.customers.models import Customer
from apps.integrations.whatsapp.service import normalize_br_phone
from .models import PendingRegistration, RegistrationRateLimit, User
from .audit import audited_otp


class OTPError(Exception):
    def __init__(self, message, *, reason="rejected"):
        super().__init__(message)
        self.reason = reason


def client_ip(request):
    from apps.core.rate_limit import get_client_ip
    return get_client_ip(request)


def create_pending(data):
    return PendingRegistration.objects.create(
        first_name=data['first_name'], last_name=data['last_name'],
        email=data['email'], phone=data['phone'],
        password_hash=make_password(data['password1']),
        expires_at=timezone.now() + timedelta(hours=24),
    )


def active(pending):
    if pending.completed_at or pending.expires_at <= timezone.now():
        raise OTPError('Este cadastro expirou ou já foi concluído. Inicie um novo cadastro.', reason='expired' if pending.expires_at <= timezone.now() else 'rejected')


def reserve_limits(pending, ip, channel):
    # Independent limits prevent bypass by changing IP, session or destination.
    now = timezone.now().timestamp()
    keys = sorted(salted_hmac('registration-rate', f'{channel}:{kind}:{value}').hexdigest()
                  for kind, value in [('ip', ip), ('email', pending.email), ('phone', pending.phone)])
    with transaction.atomic():
        buckets = []
        for key in keys:
            RegistrationRateLimit.objects.get_or_create(key=key)
            bucket = RegistrationRateLimit.objects.select_for_update().get(key=key)
            bucket.events = [event for event in bucket.events if event > now - 3600]
            if len(bucket.events) >= 5:
                raise OTPError('Limite de 5 envios por hora atingido. Tente novamente mais tarde.', reason='rate_limit')
            buckets.append(bucket)
        for bucket in buckets:
            bucket.events.append(now)
            bucket.save()


@sensitive_variables("code", "message")
def deliver(channel, pending, code):
    if channel == "email":
        message = (
            f"Olá, {pending.first_name}!\n\n"
            "Boas-vindas ao VemDeDelivery! 🍔\n\n"
            "Para confirmar seu e-mail e continuar seu cadastro, "
            "digite o código abaixo na tela de confirmação:\n\n"
            f"    {code}\n\n"
            "⏱ Este código é válido por 10 minutos "
            "e só pode ser usado uma vez.\n"
            "🔒 Para sua segurança, não compartilhe este código com ninguém.\n\n"
            "Depois desta etapa, vamos confirmar seu WhatsApp "
            "para concluir a criação da sua conta.\n\n"
            "Não iniciou este cadastro? Basta ignorar esta mensagem.\n\n"
            "Até já!\n"
            "Equipe VemDeDelivery"
        )
        sent_count = send_mail(
            subject="Falta pouco! Confirme seu e-mail | VemDeDelivery",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pending.email],
        )
        if sent_count != 1:
            raise OTPError("Não foi possível enviar o código. Tente reenviar em 60 segundos.", reason="delivery")
        return
    message = (
        f"Olá, {pending.first_name}! 👋\n\n"
        "Falta só um passo para concluir seu cadastro "
        "no *VemDeDelivery*! 🍔\n\n"
        "Digite este código na tela de confirmação do WhatsApp:\n\n"
        f"*{code}*\n\n"
        "⏱ *Válido por 10 minutos e para um único uso.*\n"
        "🔒 Não compartilhe este código com ninguém.\n\n"
        "Após a confirmação, sua conta estará pronta para fazer pedidos!\n\n"
        "Não iniciou este cadastro? Pode ignorar esta mensagem."
    )
    if not all([settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY, settings.EVOLUTION_INSTANCE]):
        raise OTPError("Envio de WhatsApp indisponível. Tente novamente mais tarde.", reason="delivery")
    response = requests.post(
        f'{settings.EVOLUTION_API_URL.rstrip("/")}/message/sendText/{quote(settings.EVOLUTION_INSTANCE, safe="")}',
        headers={"apikey": settings.EVOLUTION_API_KEY},
        json={"number": normalize_br_phone(pending.phone), "text": message},
        timeout=settings.EVOLUTION_API_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("key"), dict) or not payload["key"].get("id"):
        raise OTPError("Não foi possível confirmar o envio. Tente reenviar em 60 segundos.", reason="delivery")


@audited_otp('registration', 'send')
@sensitive_variables('code')
def send_code(pending_id, ip, channel):
    error = None
    with transaction.atomic():
        pending = PendingRegistration.objects.select_for_update().get(pk=pending_id)
        active(pending)
        if pending.channel != channel:
            raise OTPError('Esta etapa já foi concluída. Atualize a página.')
        now = timezone.now()
        if pending.last_sent_at and (now - pending.last_sent_at).total_seconds() < 60:
            raise OTPError('Aguarde 60 segundos entre os envios.', reason='cooldown')
        reserve_limits(pending, ip, channel)
        code = f'{secrets.randbelow(1000000):06d}'
        pending.code_hash = make_password(code)
        pending.code_expires_at = now + timedelta(minutes=10)
        pending.last_sent_at = now
        pending.attempts = 0
        try:
            deliver(channel, pending, code)
        except Exception:
            # Do not log provider exceptions: they can include credentials or OTPs.
            pending.code_hash = ''
            error = 'Não foi possível enviar o código. Aguarde 60 segundos e tente reenviar.'
        pending.save()
    if error:
        raise OTPError(error, reason="delivery")


@audited_otp('registration', 'verify')
@sensitive_variables('code')
def verify_code(pending_id, channel, code):
    error = None
    user = None
    error_reason = "invalid_code"
    with transaction.atomic():
        pending = PendingRegistration.objects.select_for_update().get(pk=pending_id)
        active(pending)
        now = timezone.now()
        if pending.channel != channel:
            raise OTPError('Etapa inválida. Atualize a página.')
        if not pending.code_hash or not pending.code_expires_at or pending.code_expires_at <= now:
            raise OTPError('Código expirado ou não enviado. Solicite um novo código.', reason='expired')
        if pending.attempts >= 5:
            raise OTPError('Limite de 5 tentativas atingido. Solicite um novo código.', reason='attempts')
        pending.attempts += 1
        if len(code) != 6 or not code.isascii() or not code.isdigit() or not check_password(code, pending.code_hash):
            error = 'Código inválido.'
        elif channel == 'email':
            pending.email_verified_at = now
            pending.code_hash = ''
            pending.last_sent_at = None
            pending.attempts = 0
        else:
            try:
                with transaction.atomic():
                    if User.objects.filter(Q(email__iexact=pending.email) | Q(username__iexact=pending.email)).exists():
                        raise OTPError('E-mail já cadastrado. Entre na sua conta.')
                    user = User.objects.create(
                        username=pending.email, email=pending.email, password=pending.password_hash,
                        first_name=pending.first_name, last_name=pending.last_name,
                        email_verified=True, email_verified_at=pending.email_verified_at,
                    )
                    Customer.objects.create(user=user, phone=pending.phone, phone_verified=True, phone_verified_at=now)
            except (IntegrityError, ValidationError, OTPError):
                user = None
                error_reason = 'rejected'
                error = 'E-mail ou telefone já cadastrado. Entre na sua conta ou reinicie o cadastro.'
            else:
                pending.completed_at = now
                pending.password_hash = ''
                pending.code_hash = ''
        pending.save()
    # Wrong attempts must commit even when reporting a validation error.
    if error:
        raise OTPError(error, reason=error_reason)
    return user
