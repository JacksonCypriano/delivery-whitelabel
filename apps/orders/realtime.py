"""Small Redis-backed websocket transport for the merchant order board.

Django is already served through ASGI/Uvicorn in this project. Keeping this
transport dependency-light avoids introducing a second websocket framework; a
browser that cannot keep the socket open falls back to HTTP polling.
"""

from __future__ import annotations

import asyncio
import json
from importlib import import_module
from urllib.parse import urlsplit

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY
from django.http.cookie import parse_cookie
from django.utils.crypto import constant_time_compare
import redis
import redis.asyncio as aioredis

from apps.tenants.domains import tenant_base_hostname
from apps.tenants.models import Tenant


def _redis_url():
    return (
        getattr(settings, "CACHE_REDIS_URL", "")
        or getattr(settings, "CELERY_BROKER_URL", "")
        or "redis://redis:6379/0"
    )


def _channel(tenant_id):
    return f"vdd:merchant:orders:{int(tenant_id)}"


def publish_order_event(order_id: int, tenant_id: int, event="order.updated"):
    """Best-effort realtime hint. HTTP remains authoritative."""
    payload = json.dumps(
        {"event": event, "order_id": int(order_id)}, separators=(",", ":")
    )
    client = None
    try:
        client = redis.Redis.from_url(
            _redis_url(), socket_connect_timeout=1, socket_timeout=1
        )
        client.publish(_channel(tenant_id), payload)
    except (redis.RedisError, OSError, ValueError):
        # A Redis outage must not roll back a status transition. The React board
        # polls as a fallback and will converge from the database.
        return False
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    return True


def _headers(scope):
    return {
        key.decode("latin1").lower(): value.decode("latin1")
        for key, value in scope.get("headers", [])
    }


def _tenant_slug(host_value):
    host = (urlsplit("//" + (host_value or "")).hostname or "").lower().rstrip(".")
    base = tenant_base_hostname()
    if not host or not base or host == base or not host.endswith("." + base):
        return ""
    slug = host[: -(len(base) + 1)]
    return slug if slug and "." not in slug else ""


def _same_origin(headers):
    origin = headers.get("origin", "")
    host = (urlsplit("//" + headers.get("host", "")).hostname or "").lower()
    if not origin:
        return False
    origin_host = (urlsplit(origin).hostname or "").lower()
    return bool(host and origin_host == host)


def _authenticate(headers):
    slug = _tenant_slug(headers.get("host", ""))
    if not slug:
        return None, None
    tenant = Tenant.objects.filter(slug=slug).first()
    if tenant is None:
        alias = {"demo": "vitrine-demo", "vitrine-demo": "demo"}.get(slug)
        tenant = Tenant.objects.filter(slug=alias).first() if alias else None
    if tenant is None:
        return None, None

    cookies = parse_cookie(headers.get("cookie", ""))
    key = cookies.get(settings.SESSION_COOKIE_NAME)
    if not key:
        return tenant, None
    SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
    session = SessionStore(session_key=key)
    user_id = session.get(SESSION_KEY)
    if not user_id:
        return tenant, None
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return tenant, None
    session_hash = session.get(HASH_SESSION_KEY, "")
    if session_hash and not constant_time_compare(
        session_hash, user.get_session_auth_hash()
    ):
        return tenant, None
    allowed = bool(
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.is_tenant_admin
        and not user.is_superuser
        and user.tenant_id == tenant.pk
        and not user.must_change_password
    )
    return tenant, user if allowed else None


async def merchant_orders_websocket(scope, receive, send):
    first = await receive()
    if first.get("type") != "websocket.connect":
        return
    headers = _headers(scope)
    if not _same_origin(headers):
        await send({"type": "websocket.close", "code": 4403})
        return
    tenant, user = await sync_to_async(_authenticate, thread_sensitive=True)(headers)
    if tenant is None or user is None:
        await send({"type": "websocket.close", "code": 4403})
        return

    client = aioredis.from_url(_redis_url(), decode_responses=True)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(_channel(tenant.pk))
    except (redis.RedisError, OSError, ValueError):
        await pubsub.close()
        await client.aclose()
        await send({"type": "websocket.close", "code": 1013})
        return

    await send({"type": "websocket.accept"})
    await send(
        {
            "type": "websocket.send",
            "text": json.dumps({"event": "connected"}),
        }
    )

    receive_task = asyncio.create_task(receive())
    redis_task = asyncio.create_task(
        pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
    )
    try:
        while True:
            done, _ = await asyncio.wait(
                {receive_task, redis_task},
                timeout=25,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                await send(
                    {
                        "type": "websocket.send",
                        "text": json.dumps({"event": "ping"}),
                    }
                )
                continue

            if receive_task in done:
                incoming = receive_task.result()
                if incoming.get("type") == "websocket.disconnect":
                    break
                receive_task = asyncio.create_task(receive())

            if redis_task in done:
                message = redis_task.result()
                if message and message.get("type") == "message":
                    await send(
                        {"type": "websocket.send", "text": str(message.get("data", ""))}
                    )
                redis_task = asyncio.create_task(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
                )
    except (redis.RedisError, OSError, asyncio.CancelledError):
        pass
    finally:
        for task in (receive_task, redis_task):
            if not task.done():
                task.cancel()
        try:
            await pubsub.unsubscribe(_channel(tenant.pk))
            await pubsub.close()
            await client.aclose()
        except Exception:
            pass
