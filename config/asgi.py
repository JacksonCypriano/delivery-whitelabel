"""ASGI entrypoint with the merchant order realtime websocket."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Initialise Django before importing app modules used by the websocket handler.
django_application = get_asgi_application()

from apps.orders.realtime import merchant_orders_websocket  # noqa: E402


async def application(scope, receive, send):
    if scope.get("type") == "websocket":
        if scope.get("path") == "/ws/merchant/orders/":
            await merchant_orders_websocket(scope, receive, send)
            return
        await send({"type": "websocket.close", "code": 4404})
        return
    await django_application(scope, receive, send)
