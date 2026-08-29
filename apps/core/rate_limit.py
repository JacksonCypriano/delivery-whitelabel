import hashlib

from django.core.cache import cache


def get_client_ip(request):
    real_ip = request.META.get("HTTP_X_REAL_IP", "").strip()
    if real_ip:
        return real_ip
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown") or "unknown"


def _key(scope, request, identifier=""):
    raw = f"{scope}|{get_client_ip(request)}|{identifier.strip().casefold()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"security:rate-limit:{scope}:{digest}"


def rate_limit_exceeded(request, scope, identifier="", limit=5, window=300):
    key = _key(scope, request, identifier)
    if cache.add(key, 1, timeout=window):
        return False
    try:
        attempts = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        attempts = 1
    return attempts > limit


def clear_rate_limit(request, scope, identifier=""):
    cache.delete(_key(scope, request, identifier))
