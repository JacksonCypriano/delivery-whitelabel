from urllib.parse import urlencode

from django.conf import settings


def build_tenant_url(tenant, query=None):
    scheme = getattr(settings, "TENANT_PUBLIC_SCHEME", "http")
    base_domain = getattr(settings, "TENANT_BASE_DOMAIN", "lvh.me:8000").strip()

    url = f"{scheme}://{tenant.slug}.{base_domain}/"

    if query:
        url += "?" + urlencode(query)

    return url


def get_brand_logo_url(tenant):
    try:
        brand = tenant.brand_config
    except Exception:
        return ""

    try:
        return brand.logo.url if brand.logo else ""
    except Exception:
        return ""
