import hashlib
import ipaddress

from django.conf import settings

from django.core.cache import cache


def get_client_ip(request):
    value = request.META.get("REMOTE_ADDR", "")
    try:
        peer = ipaddress.ip_address(value.strip())
    except (ValueError, AttributeError):
        return "unknown"
    if getattr(settings, "OTP_TRUST_PROXY_HEADERS", False):
        networks = getattr(settings, "OTP_TRUSTED_PROXY_CIDRS", [])
        try:
            trusted = any(peer in ipaddress.ip_network(cidr.strip()) for cidr in networks)
        except ValueError:
            trusted = False
        if trusted:
            value = request.META.get("HTTP_X_REAL_IP") or str(peer)
    try:
        return str(ipaddress.ip_address(value.strip()))
    except (ValueError, AttributeError):
        return "unknown"


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


def identifier_rate_limit_exceeded(scope, identifier, limit=5, window=300):
    raw = f"{scope}|{str(identifier).strip().casefold()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    key = f"security:rate-limit:{scope}:{digest}"
    if cache.add(key, 1, timeout=window):
        return False
    try:
        attempts = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        attempts = 1
    return attempts > limit


def distinct_identifier_rate_limit_exceeded(scope, owner, identifier, limit=5, window=900):
    owner_digest = hashlib.sha256(str(owner).strip().casefold().encode("utf-8")).hexdigest()
    value_digest = hashlib.sha256(str(identifier).strip().casefold().encode("utf-8")).hexdigest()
    member_key = f"security:rate-limit:{scope}:member:{owner_digest}:{value_digest}"
    counter_key = f"security:rate-limit:{scope}:count:{owner_digest}"

    # Repetir o mesmo valor não consome uma nova posição, mas não pode
    # contornar um limite que já foi ultrapassado por esse proprietário.
    if not cache.add(member_key, 1, timeout=window):
        try:
            return int(cache.get(counter_key) or 0) > limit
        except (TypeError, ValueError):
            return False

    if cache.add(counter_key, 1, timeout=window):
        return False
    try:
        distinct_values = cache.incr(counter_key)
    except ValueError:
        cache.set(counter_key, 1, timeout=window)
        distinct_values = 1
    return distinct_values > limit
