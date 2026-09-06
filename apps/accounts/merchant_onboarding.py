import logging
import secrets
import string
from functools import partial
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.marketplace.services import build_tenant_url

logger = logging.getLogger("vemdedelivery.accounts")


_PASSWORD_SYMBOLS = "!@#$%&*+-_"
_PASSWORD_ALPHABET = string.ascii_letters + string.digits + _PASSWORD_SYMBOLS


def generate_temporary_password(length=16):
    """Gera uma credencial forte sem depender de estado pseudoaleatório previsível."""
    length = max(12, int(length))
    chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(_PASSWORD_SYMBOLS),
    ]
    chars.extend(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def build_merchant_access_urls(tenant):
    store_url = build_tenant_url(tenant)
    return store_url, urljoin(store_url, "admin/")


@sensitive_variables("temporary_password")
def send_merchant_welcome_email(user_id, temporary_password):
    """Envia a credencial apenas por e-mail e nunca a persiste em texto puro."""
    from .models import User

    user = User.objects.select_related("tenant").filter(pk=user_id).first()
    if not user or not user.tenant_id or not user.email:
        logger.error("Boas-vindas do lojista não enviadas: conta sem loja ou e-mail.")
        return False

    store_url, admin_url = build_merchant_access_urls(user.tenant)
    context = {
        "user": user,
        "tenant": user.tenant,
        "login": user.username,
        "temporary_password": temporary_password,
        "store_url": store_url,
        "admin_url": admin_url,
    }
    subject = f"Bem-vindo ao VemDeDelivery — acesso à {user.tenant.name}"
    text_body = render_to_string("accounts/merchant_welcome_email.txt", context)
    html_body = render_to_string("accounts/merchant_welcome_email.html", context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")
    sent = message.send(fail_silently=False)
    if sent != 1:
        raise RuntimeError("O provedor de e-mail não confirmou o envio.")

    sent_at = timezone.now()
    User.objects.filter(pk=user.pk).update(welcome_email_sent_at=sent_at)
    return True


@sensitive_variables("temporary_password")
def _safe_send_merchant_welcome_email(user_id, temporary_password):
    try:
        return send_merchant_welcome_email(user_id, temporary_password)
    except Exception:
        # Não registra login, senha temporária, destinatário ou payload do provedor.
        logger.error("Falha no envio do e-mail de boas-vindas do lojista.")
        return False


@sensitive_variables("temporary_password")
def schedule_merchant_welcome_email(user_id, temporary_password):
    """Só dispara depois que a conta estiver efetivamente gravada no banco."""
    transaction.on_commit(
        partial(_safe_send_merchant_welcome_email, user_id, temporary_password)
    )
