"""Confirm contact changes without modifying the current contact before OTP.

Lock order: User -> Customer -> PendingContactChange -> rate-limit buckets.
All entry points use the same order, including replacement and cancellation.
"""
import secrets
from datetime import timedelta
from types import SimpleNamespace

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
from .models import PendingContactChange, RegistrationRateLimit, User
from .otp import OTPError, reserve_limits
from .audit import audited_otp


def pending_changes(user):
    return PendingContactChange.objects.filter(
        user=user, completed_at__isnull=True, cancelled_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).order_by("channel")


def _lock_account(user_id):
    user = User.objects.select_for_update().get(pk=user_id)
    if not user.is_active or user.is_staff or user.is_superuser or user.is_tenant_admin or user.tenant_id:
        raise OTPError("Esta operação é exclusiva de contas de cliente ativas.")
    try:
        customer = Customer.objects.select_for_update().get(user_id=user_id)
    except Customer.DoesNotExist:
        raise OTPError("Conta de cliente não encontrada.") from None
    return user, customer


def _available(channel, destination, user_id):
    if channel == "email":
        exists = User.objects.exclude(pk=user_id).filter(
            Q(email__iexact=destination) | Q(username__iexact=destination)
        ).exists()
    else:
        exists = Customer.objects.exclude(user_id=user_id).filter(phone=destination).exists()
    if exists:
        raise OTPError("Este contato já está cadastrado em outra conta. Informe outro contato.")


def _current(user, customer, channel):
    return user.email if channel == "email" else customer.phone


def _active(pending, user, customer):
    if pending.completed_at or pending.cancelled_at or pending.expires_at <= timezone.now():
        raise OTPError("Esta solicitação expirou ou já foi encerrada. Volte aos seus dados.", reason="expired" if pending.expires_at <= timezone.now() else "rejected")
    if pending.original_value != _current(user, customer, pending.channel):
        raise OTPError("Seu contato foi alterado desde esta solicitação. Volte aos seus dados e tente novamente.")


def _lock_pending(user_id, pending_id):
    try:
        return PendingContactChange.objects.select_for_update().get(pk=pending_id, user_id=user_id)
    except PendingContactChange.DoesNotExist:
        raise OTPError("Solicitação não encontrada. Volte aos seus dados.") from None


@transaction.atomic
def save_profile(user_id, data):
    """Update names immediately; stage contacts. Repeated submissions retain OTP state."""
    user, customer = _lock_account(user_id)
    user.first_name = data["first_name"]
    user.last_name = data["last_name"]
    user.save(update_fields=["first_name", "last_name"])
    staged = []
    for channel, destination in [("email", data["email"]), ("whatsapp", data["phone"])]:
        original = _current(user, customer, channel)
        if destination == original:
            continue
        _available(channel, destination, user_id)
        previous = PendingContactChange.objects.select_for_update().filter(user_id=user_id, channel=channel).first()
        now = timezone.now()
        if (previous and not previous.completed_at and not previous.cancelled_at
                and previous.expires_at > now and previous.destination == destination
                and previous.original_value == original):
            staged.append(previous)
            continue
        # Preserve cooldown even across cancel/restart or a change of destination.
        last_sent = previous.last_sent_at if previous else None
        if previous:
            previous.delete()
        staged.append(PendingContactChange.objects.create(
            user=user, channel=channel, destination=destination, original_value=original,
            expires_at=now + timedelta(hours=24), last_sent_at=last_sent,
        ))
    return user, staged


def _reserve_send(user, customer, pending, ip):
    # Additional account-level limit stops rotating destination/IP combinations.
    key = salted_hmac("contact-account-rate", f"{user.pk}:{pending.channel}").hexdigest()
    RegistrationRateLimit.objects.get_or_create(key=key)
    bucket = RegistrationRateLimit.objects.select_for_update().get(pk=key)
    now = timezone.now().timestamp()
    bucket.events = [event for event in bucket.events if event > now - 3600]
    if len(bucket.events) >= 5:
        raise OTPError("Limite de 5 envios por hora atingido. Tente novamente mais tarde.", reason="rate_limit")
    contacts = SimpleNamespace(
        email=pending.destination if pending.channel == "email" else user.email,
        phone=pending.destination if pending.channel == "whatsapp" else customer.phone,
    )
    # Reuse registration buckets: changing the flow cannot reset destination/IP limits.
    reserve_limits(contacts, ip, pending.channel)
    bucket.events.append(now)
    bucket.save()


@sensitive_variables("code", "message")
def deliver_contact_code(pending, user, code):
    """Separate copy for profile changes; registration's deliver() is untouched."""
    if pending.channel == "email":
        message = (
            f"Olá, {user.first_name}!\n\n"
            "Recebemos uma solicitação para alterar o e-mail da sua conta no VemDeDelivery.\n\n"
            "Para confirmar este novo endereço, digite o código na tela de confirmação:\n\n"
            f"    {code}\n\n"
            "⏱ Este código é válido por 10 minutos e só pode ser usado uma vez.\n"
            "🔒 Não compartilhe este código com ninguém.\n\n"
            "Seu e-mail atual continua válido até a confirmação. Depois disso, "
            "use este novo endereço para entrar na sua conta.\n\n"
            "Não solicitou esta alteração? Ignore esta mensagem. "
            "Sem a confirmação, seu e-mail não será alterado.\n\n"
            "Equipe VemDeDelivery"
        )
        if send_mail("Confirme seu novo e-mail | VemDeDelivery", message,
                     settings.DEFAULT_FROM_EMAIL, [pending.destination]) != 1:
            raise OTPError("Não foi possível enviar o código.")
        return
    message = (
        f"Olá, {user.first_name}! 👋\n\n"
        "Vamos confirmar seu novo WhatsApp no *VemDeDelivery*.\n\n"
        "Digite este código na tela de confirmação:\n\n"
        f"*{code}*\n\n"
        "⏱ *Válido por 10 minutos e para um único uso.*\n"
        "🔒 Não compartilhe este código com ninguém.\n\n"
        "Seu telefone atual será substituído somente após a confirmação.\n\n"
        "Não solicitou esta alteração? Pode ignorar esta mensagem. "
        "Sem a confirmação, seu telefone não será alterado."
    )
    if not all([settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY, settings.EVOLUTION_INSTANCE]):
        raise OTPError("Envio de WhatsApp indisponível.")
    from apps.integrations.whatsapp.client import phone_otp_transport, EvolutionError
    try:
        phone_otp_transport().send_phone_code(normalize_br_phone(pending.destination), message)
    except EvolutionError:
        raise OTPError("Não foi possível confirmar o envio.", reason="delivery") from None


@audited_otp("contact", "send")
@sensitive_variables("code")
def send_contact_code(user_id, pending_id, ip):
    error = None
    with transaction.atomic():
        user, customer = _lock_account(user_id)
        pending = _lock_pending(user_id, pending_id)
        _active(pending, user, customer)
        _available(pending.channel, pending.destination, user_id)
        now = timezone.now()
        if pending.last_sent_at and (now - pending.last_sent_at).total_seconds() < 60:
            raise OTPError("Aguarde 60 segundos entre os envios.", reason="cooldown")
        _reserve_send(user, customer, pending, ip)
        code = f"{secrets.randbelow(1000000):06d}"
        pending.code_hash = make_password(code)
        pending.code_expires_at = now + timedelta(minutes=10)
        pending.last_sent_at = now
        pending.attempts = 0
        try:
            deliver_contact_code(pending, user, code)
        except Exception:
            # Provider errors can include tokens/OTP. Do not log their raw content.
            pending.code_hash = ""
            error = "Não foi possível enviar o código. Seu contato atual foi mantido. Aguarde 60 segundos e tente reenviar."
        pending.save()
    if error:
        raise OTPError(error, reason="delivery")


@audited_otp("contact", "verify")
@sensitive_variables("code")
def verify_contact_code(user_id, pending_id, code):
    error = None
    error_reason = "invalid_code"
    with transaction.atomic():
        user, customer = _lock_account(user_id)
        pending = _lock_pending(user_id, pending_id)
        _active(pending, user, customer)
        now = timezone.now()
        if not pending.code_hash or not pending.code_expires_at or pending.code_expires_at <= now:
            raise OTPError("Código expirado ou não enviado. Solicite um novo código.", reason="expired")
        if pending.attempts >= 5:
            raise OTPError("Limite de 5 tentativas atingido. Solicite um novo código.", reason="attempts")
        pending.attempts += 1
        if len(code) != 6 or not code.isascii() or not code.isdigit() or not check_password(code, pending.code_hash):
            error = "Código inválido. Confira os 6 dígitos recebidos."
        else:
            try:
                # Savepoint rolls back identity changes on uniqueness races.
                with transaction.atomic():
                    _available(pending.channel, pending.destination, user_id)
                    if pending.channel == "email":
                        user.email = pending.destination
                        user.username = pending.destination
                        user.email_verified = True
                        user.email_verified_at = now
                        user.save(update_fields=["email", "username", "email_verified", "email_verified_at"])
                    else:
                        customer.phone = pending.destination
                        customer.phone_verified = True
                        customer.phone_verified_at = now
                        customer.save(update_fields=["phone", "phone_verified", "phone_verified_at", "updated_at"])
            except (IntegrityError, ValidationError, OTPError):
                error_reason = "rejected"
                error = "Não foi possível atualizar: este contato pode ter sido cadastrado em outra conta. Volte aos seus dados."
                pending.cancelled_at = now
                pending.code_hash = ""
            else:
                pending.completed_at = now
                pending.code_hash = ""
        pending.save()
    # Wrong attempts are committed, rather than undone by an exception.
    if error:
        raise OTPError(error, reason=error_reason)
    return pending.channel


@audited_otp("contact", "cancel")
@transaction.atomic
def cancel_contact_change(user_id, pending_id):
    _lock_account(user_id)
    pending = _lock_pending(user_id, pending_id)
    if pending.completed_at:
        raise OTPError("Esta alteração já foi confirmada.")
    pending.cancelled_at = timezone.now()
    pending.code_hash = ""
    pending.save(update_fields=["cancelled_at", "code_hash"])
