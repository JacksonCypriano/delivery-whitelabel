"""99Food sandbox shop authentication based on the portal's supplied OpenAPI.

No automatic activation of webhooks, ordering or production integrations.
"""

import hashlib
from datetime import datetime, timedelta, timezone as dt_timezone

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.secrets import decrypt_secret, encrypt_secret
from .models import AppToken
from .connectors import ProviderError

BASE_URL = "https://openapi.didi-food.com"


def _configuration(app_shop_id):
    if not getattr(settings, "FOOD99_SANDBOX_ENABLED", False):
        raise ProviderError("99Food sandbox desabilitado.")
    if not app_shop_id or not isinstance(app_shop_id, str) or len(app_shop_id) > 255:
        raise ProviderError("AppShopID inválido.")
    app_id = getattr(settings, "FOOD99_TEST_APP_ID", "")
    secret = getattr(settings, "FOOD99_TEST_APP_SECRET", "")
    if not str(app_id).isdigit() or not secret:
        raise ProviderError("Credenciais da 99Food sandbox não configuradas.")
    return str(app_id), secret


def _call(path, app_id, secret, app_shop_id):
    # The supplied Swagger requires app_secret in query parameters. Never log
    # requests, URLs, responses or exception objects containing these secrets.
    try:
        response = requests.get(
            BASE_URL + path,
            params={"app_id": app_id, "app_secret": secret, "app_shop_id": app_shop_id},
            timeout=(5, 15),
            allow_redirects=False,
        )
    except requests.RequestException:
        raise ProviderError("99Food indisponível ou conexão não autorizada.", retryable=True) from None
    if response.status_code != 200:
        raise ProviderError("Falha de autenticação 99Food (HTTP %s)." % response.status_code,
                            retryable=response.status_code >= 500, status_code=response.status_code)
    try:
        data = response.json()
    except ValueError:
        raise ProviderError("Resposta inválida da autenticação 99Food.") from None
    if not isinstance(data, dict) or data.get("errno") != 0:
        raise ProviderError("Autenticação da 99Food recusada.")
    return data.get("data")


def _expires_at(value):
    # OpenAPI defines an integer but does not state whether it uses seconds or
    # milliseconds. Reject ambiguous values instead of caching an incorrect TTL.
    try:
        number = int(value)
        if number > 10**12:
            number /= 1000
        if number < 10**9:
            raise ValueError
        result = datetime.fromtimestamp(number, tz=dt_timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        raise ProviderError("Expiração do token 99Food não reconhecida.") from None
    if result <= timezone.now() + timedelta(seconds=30):
        raise ProviderError("Token 99Food expirado ou próximo da expiração.")
    return result


@transaction.atomic
def get_shop_token(app_shop_id, *, force_refresh=False):
    """Cache encrypted tokens per application/shop, refreshing under row lock."""
    app_id, secret = _configuration(app_shop_id)
    key = "99food:" + hashlib.sha256((app_id + ":" + app_shop_id).encode()).hexdigest()[:32]
    AppToken.objects.get_or_create(key=key)
    row = AppToken.objects.select_for_update().get(key=key)
    if not force_refresh and row.encrypted_token and row.expires_at and row.expires_at > timezone.now() + timedelta(minutes=5):
        return decrypt_secret(row.encrypted_token)
    # Token ausente/expirado: renovar PRIMEIRO, inclusive sem --refresh.
    # Uma consulta /get isolada pode devolver uma autorização vencida.
    result = _call("/v1/auth/authtoken/refresh", app_id, secret, app_shop_id)
    if result is not True:
        raise ProviderError("99Food não confirmou renovação do token.")
    payload = _call("/v1/auth/authtoken/get", app_id, secret, app_shop_id)
    if not isinstance(payload, dict):
        raise ProviderError("Token 99Food ausente.")
    token = payload.get("auth_token")
    if (not isinstance(token, str) or not token or
            str(payload.get("app_id")) != app_id or payload.get("app_shop_id") != app_shop_id):
        raise ProviderError("Dados do token 99Food inválidos.")
    expiration = _expires_at(payload.get("token_expiration_time"))
    row.encrypted_token = encrypt_secret(token)
    row.expires_at = expiration
    row.save(update_fields=["encrypted_token", "expires_at"])
    return token
