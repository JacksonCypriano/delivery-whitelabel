"""Read-only 99Food sandbox order detail adapter.

Based on the application portal's swagger.yaml (/v1/order/order/detail).
Do not log URLs, requests or responses: auth_token is a query parameter and
order details contain customer personal information.
"""
import re
import requests
from django.conf import settings
from .connectors import ProviderError
from .food99_auth import BASE_URL, get_shop_token

ORDER_ID_PATTERN = re.compile(r"^[0-9]{1,30}$")


def get_order_detail(app_shop_id: str, order_id: str) -> dict:
    """Read the sandbox order, without modifying local orders or acknowledging an event."""
    if not getattr(settings, "FOOD99_SANDBOX_ENABLED", False):
        raise ProviderError("99Food sandbox desabilitado.")
    order_id = str(order_id)
    if not ORDER_ID_PATTERN.fullmatch(order_id):
        raise ProviderError("ID do pedido 99Food inválido.")
    token = get_shop_token(app_shop_id)
    try:
        response = requests.get(
            BASE_URL + "/v1/order/order/detail",
            params={"auth_token": token, "order_id": order_id},
            timeout=(5, 15), allow_redirects=False,
        )
    except requests.RequestException:
        raise ProviderError("Falha de conexão ao consultar pedido 99Food.", retryable=True) from None
    if response.status_code != 200:
        raise ProviderError("Falha ao consultar pedido 99Food (HTTP %s)." % response.status_code,
                            retryable=response.status_code >= 500, status_code=response.status_code)
    try:
        payload = response.json()
    except ValueError:
        raise ProviderError("Resposta JSON inválida da 99Food.") from None
    if not isinstance(payload, dict) or payload.get("errno") != 0:
        raise ProviderError("99Food recusou a consulta do pedido.")
    details = payload.get("data")
    if not isinstance(details, dict):
        raise ProviderError("Detalhes do pedido 99Food ausentes.")
    return details
