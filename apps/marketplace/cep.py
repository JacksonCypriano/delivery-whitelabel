import json
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache


CEP_RE = re.compile(r"^\d{8}$")


class CepLookupError(Exception):
    pass


class CepNotFound(CepLookupError):
    pass


def normalize_cep(value):
    return re.sub(r"\D", "", str(value or ""))


def is_valid_cep(value):
    return bool(
        CEP_RE.fullmatch(
            normalize_cep(value)
        )
    )


def lookup_cep(value):
    cep = normalize_cep(value)

    if not CEP_RE.fullmatch(cep):
        raise ValueError(
            "CEP deve conter exatamente 8 dígitos."
        )

    cache_seconds = int(
        getattr(
            settings,
            "MARKETPLACE_CEP_CACHE_SECONDS",
            60 * 60 * 24 * 30,
        )
    )

    cache_key = f"marketplace:cep:{cep}"
    cached = cache.get(cache_key)

    if cached is not None:
        if cached == "__not_found__":
            raise CepNotFound(
                "CEP não encontrado."
            )

        return cached

    base_url = getattr(
        settings,
        "MARKETPLACE_CEP_URL",
        "https://viacep.com.br/ws/{cep}/json/",
    )

    timeout = float(
        getattr(
            settings,
            "MARKETPLACE_CEP_TIMEOUT",
            4,
        )
    )

    user_agent = getattr(
        settings,
        "MARKETPLACE_CEP_USER_AGENT",
        "VemDeDelivery/1.0",
    )

    request = urllib.request.Request(
        base_url.format(cep=cep),
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        raise CepLookupError(
            "Não foi possível consultar o CEP agora."
        ) from exc

    if payload.get("erro") is True:
        cache.set(
            cache_key,
            "__not_found__",
            min(
                cache_seconds,
                60 * 60 * 24,
            ),
        )

        raise CepNotFound(
            "CEP não encontrado."
        )

    result = {
        "cep": str(payload.get("cep") or "").strip(),
        "street": str(payload.get("logradouro") or "").strip(),
        "complement": str(payload.get("complemento") or "").strip(),
        "neighborhood": str(payload.get("bairro") or "").strip(),
        "city": str(payload.get("localidade") or "").strip(),
        "state": str(payload.get("uf") or "").strip().upper()[:2],
        "ibge": str(payload.get("ibge") or "").strip(),
        "source": "viacep",
    }

    cache.set(
        cache_key,
        result,
        cache_seconds,
    )

    return result
