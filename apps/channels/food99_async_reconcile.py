"""Opt-in, HML-only asynchronous reconciliation of quarantined 99Food webhooks.

This is *not* a live webhook consumer. It never ACKs 99Food, promotes an Order,
changes KDS/stock/payments, sends a provider command, or enables a connection.
The task only performs the same read-only GET and encrypted staging as the
approved reconcile_99food_webhook command.
"""

from django.conf import settings

from .connectors import ProviderError
from .food99_webhook_reconcile import _guard, _eligible, reconcile
from .models import Inbox


def _async_guard():
    _guard()
    if getattr(settings, "FOOD99_ASYNC_RECONCILE_ENABLED", False) is not True:
        raise ProviderError("Consumidor 99Food assíncrono desativado.")


def select_event_ids(*, tenant_slug, limit=20):
    """Read a bounded, deterministic set; no events or Orders are modified."""
    _async_guard()
    if not isinstance(tenant_slug, str) or not tenant_slug or len(tenant_slug) > 100:
        raise ProviderError("Tenant inválido.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ProviderError("Limite de eventos deve estar entre 1 e 100.")
    candidates = Inbox.objects.select_related("connection__tenant").filter(
        state="blocked",
        connection__provider="99food",
        connection__mode="test",
        connection__enabled=False,
        connection__tenant__slug=tenant_slug,
        payload__food99_quarantined=True,
    ).order_by("received_at", "pk")[:limit]
    selected = []
    for event in candidates:
        try:
            _eligible(event)
        except ProviderError:
            continue
        selected.append(event.pk)
    return selected


def reconcile_one(event_id):
    """Called only by the explicit Celery task; rechecks every guard at runtime."""
    _async_guard()
    result = reconcile(event_id, apply=True)
    return {
        "event_id": result["event_id"],
        "state": result["state"],
        "staged": result["staged"],
        "acknowledged": False,
        "operational": False,
    }


def queue_reconciliation(*, tenant_slug, limit=20, enqueue=None):
    """Queue opt-in jobs; never execute a provider GET in the HTTP callback.

    The caller must provide a Celery .delay function. An unavailable broker is
    reported to the operator rather than silently claiming the events ran.
    """
    ids = select_event_ids(tenant_slug=tenant_slug, limit=limit)
    if enqueue is None:
        return {"selected": len(ids), "queued": 0, "event_ids": ids,
                "mode": "preview", "acknowledged": False}
    queued = []
    for event_id in ids:
        # Let broker exceptions propagate; no success is fabricated on failure.
        enqueue(event_id)
        queued.append(event_id)
    return {"selected": len(ids), "queued": len(queued),
            "event_ids": queued, "mode": "queued", "acknowledged": False}
