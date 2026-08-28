import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache


DEFAULT_GEOCODER_URL = "https://nominatim.openstreetmap.org/reverse"


def _clean(value):
    return (value or "").strip()


def reverse_geocode(latitude, longitude):
    enabled = getattr(
        settings,
        "MARKETPLACE_GEOCODER_ENABLED",
        True,
    )

    if not enabled:
        return None

    provider_url = getattr(
        settings,
        "MARKETPLACE_GEOCODER_URL",
        DEFAULT_GEOCODER_URL,
    ).strip()

    user_agent = getattr(
        settings,
        "MARKETPLACE_GEOCODER_USER_AGENT",
        "VemDeDelivery/1.0 (+https://vemdedelivery.com.br)",
    ).strip()

    timeout = int(
        getattr(
            settings,
            "MARKETPLACE_GEOCODER_TIMEOUT",
            4,
        )
    )

    cache_seconds = int(
        getattr(
            settings,
            "MARKETPLACE_GEOCODER_CACHE_SECONDS",
            604800,
        )
    )

    rounded_latitude = round(float(latitude), 4)
    rounded_longitude = round(float(longitude), 4)

    cache_key = (
        "marketplace:reverse_geocode:"
        f"{rounded_latitude}:{rounded_longitude}"
    )

    cached = cache.get(cache_key)

    if cached is not None:
        return cached

    lock_key = "marketplace:reverse_geocode:provider_lock"
    lock_acquired = cache.add(lock_key, "1", timeout=2)

    if not lock_acquired:
        return None

    try:
        query = urlencode({
            "format": "jsonv2",
            "lat": latitude,
            "lon": longitude,
            "addressdetails": 1,
            "zoom": 18,
        })

        request = Request(
            f"{provider_url}?{query}",
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Accept-Language": "pt-BR,pt;q=0.9",
            },
        )

        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        address = payload.get("address") or {}

        city = (
            address.get("city")
            or address.get("town")
            or address.get("municipality")
            or address.get("village")
            or ""
        )

        neighborhood = (
            address.get("suburb")
            or address.get("neighbourhood")
            or address.get("quarter")
            or address.get("city_district")
            or ""
        )

        state = (address.get("state_code") or "").replace(
            "BR-",
            "",
        ).upper()

        result = {
            "city": _clean(city),
            "state": _clean(state),
            "neighborhood": _clean(neighborhood),
            "road": _clean(address.get("road")),
            "postcode": _clean(address.get("postcode")),
            "display_name": _clean(payload.get("display_name")),
        }

        cache.set(cache_key, result, timeout=cache_seconds)
        return result

    except Exception:
        return None

    finally:
        cache.delete(lock_key)
