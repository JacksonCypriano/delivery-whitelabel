"""Cliente Asaas: destinos fixos, sem registrar tokens ou respostas com dados pessoais."""

import re
from urllib.parse import urlparse
import requests
from django.conf import settings


class BillingError(Exception):
    pass


class ProviderUnavailable(BillingError):
    pass


class ProviderRejected(BillingError):
    pass


def environment():
    value = settings.ASAAS_ENVIRONMENT
    if value not in ("sandbox", "production"):
        raise BillingError("Ambiente Asaas inválido.")
    return value


def configured():
    allowed = environment() != "sandbox" or getattr(
        settings, "BILLING_ALLOW_SANDBOX", True
    )
    return bool(
        allowed
        and settings.BILLING_ENABLED
        and settings.ASAAS_API_KEY
        and len(settings.ASAAS_WEBHOOK_TOKEN) >= 32
    )


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", value):
        raise BillingError("Identificador do provedor inválido.")
    return value


def payment_url(value):
    if not isinstance(value, str):
        return ""
    try:
        u = urlparse(value)
        port = u.port
    except ValueError:
        return ""
    allowed = (
        {"www.asaas.com", "asaas.com"}
        if environment() == "production"
        else {"sandbox.asaas.com"}
    )
    if (
        u.scheme != "https"
        or u.hostname not in allowed
        or u.username
        or u.password
        or port not in (None, 443)
    ):
        return ""
    return value


class Asaas:
    def request(self, method, path, **kwargs):
        if not configured():
            raise BillingError("Pagamentos ainda não configurados. Fale com o suporte.")
        base = (
            "https://api.asaas.com/v3"
            if environment() == "production"
            else "https://api-sandbox.asaas.com/v3"
        )
        try:
            r = requests.request(
                method,
                base + path,
                headers={
                    "access_token": settings.ASAAS_API_KEY,
                    "User-Agent": "VemDeDelivery-Billing/1.0",
                },
                timeout=(4, 12),
                allow_redirects=False,
                **kwargs
            )
            if r.status_code in (400, 401, 403, 422):
                raise ProviderRejected(
                    "O Asaas recusou a operação. Confira os dados do pagador e a configuração da conta antes de tentar novamente."
                )
            if r.status_code >= 400 or r.status_code < 200 or r.status_code >= 300:
                raise ProviderUnavailable(
                    "O Asaas não concluiu a operação. A cobrança será conciliada antes de nova tentativa."
                )
            data = r.json()
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (requests.RequestException, ValueError) as exc:
            raise ProviderUnavailable(
                "Não foi possível confirmar a resposta do Asaas. Tente consultar novamente em alguns minutos."
            ) from None

    def find_payment(self, reference):
        return self.request(
            "GET", "/payments", params={"externalReference": reference, "limit": 100}
        )

    def get_payment(self, identifier):
        return self.request("GET", "/payments/" + valid_id(identifier))

    def create_payment(self, body):
        return self.request("POST", "/payments", json=body)

    def find_customer(self, reference):
        return self.request(
            "GET", "/customers", params={"externalReference": reference, "limit": 100}
        )

    def create_customer(self, body):
        return self.request("POST", "/customers", json=body)

    def pix(self, identifier):
        return self.request("GET", "/payments/" + valid_id(identifier) + "/pixQrCode")
