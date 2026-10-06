"""Host helpers used to keep platform and tenant administration isolated."""

from urllib.parse import urlsplit

from django.conf import settings


def _hostname(value):
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    return (parsed.hostname or "").rstrip(".").lower()


def request_hostname(request):
    return _hostname(request.get_host())


def tenant_base_hostname():
    return _hostname(settings.TENANT_BASE_DOMAIN)


def platform_hostnames():
    """Configured root hosts that may expose the global administration."""
    candidates = {
        tenant_base_hostname(),
        _hostname(getattr(settings, "CUSTOMER_PORTAL_URL", "")),
        _hostname(getattr(settings, "MARKETING_PUBLIC_URL", "")),
        _hostname(getattr(settings, "SUPERADMIN_PUBLIC_URL", "")),
    }
    candidates.update(
        _hostname(value)
        for value in getattr(settings, "PLATFORM_ADMIN_HOST_ALIASES", ())
    )
    return {host for host in candidates if host}


def is_platform_host(request):
    """True only for an explicitly configured root host, never a tenant subdomain."""
    return request_hostname(request) in platform_hostnames()


def tenant_slug_from_request(request):
    """Return the single tenant subdomain, or None for root/unknown hosts."""
    host = request_hostname(request)
    base = tenant_base_hostname()
    if not host or not base or host == base:
        return None

    suffix = "." + base
    if not host.endswith(suffix):
        return None

    slug = host[: -len(suffix)]
    # Tenant URLs are deliberately one level deep: slug.dominio.
    if not slug or "." in slug:
        return None
    return slug
