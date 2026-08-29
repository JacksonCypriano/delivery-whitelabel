import logging
import time
import uuid

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


logger = logging.getLogger("vemdedelivery.health")


@never_cache
@require_GET
def live(request):
    return JsonResponse({"status": "ok", "service": "vemdedelivery"})


@never_cache
@require_GET
def ready(request):
    started = time.monotonic()
    checks = {"database": False, "redis": False}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = True
    except Exception:
        logger.exception("Readiness database check failed")

    key = f"health:{uuid.uuid4().hex}"
    try:
        cache.set(key, "ok", timeout=10)
        checks["redis"] = cache.get(key) == "ok"
        cache.delete(key)
    except Exception:
        logger.exception("Readiness redis check failed")

    healthy = all(checks.values())
    return JsonResponse(
        {
            "status": "ok" if healthy else "unavailable",
            "checks": checks,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        },
        status=200 if healthy else 503,
    )
