from decimal import Decimal, InvalidOperation
import re
import unicodedata

from .models import DeliveryZone


ZERO = Decimal("0.00")


def _to_decimal(value, default="0.00"):
    try:
        if value in (None, ""):
            return Decimal(default)

        if isinstance(value, Decimal):
            return value

        return Decimal(str(value))

    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def normalize_location_text(value):
    """
    Normaliza cidade/bairro apenas para comparação comercial.

    Exemplos:
        "São Paulo"   -> "sao paulo"
        "  Vila   Y " -> "vila y"

    Não tenta adivinhar abreviações como "Jd." = "Jardim".
    """
    value = str(value or "").strip().casefold()

    if not value:
        return ""

    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def format_delivery_fee(value):
    value = _to_decimal(value).quantize(Decimal("0.01"))

    if value <= ZERO:
        return "Grátis"

    return f"R$ {value:.2f}".replace(".", ",")


def resolve_delivery(
    tenant,
    delivery_type="delivery",
    city="",
    neighborhood="",
):
    """
    Fonte única da regra de atendimento/frete.

    Regras:
    1. Retirada sempre tem frete zero.
    2. Se a loja não aceita delivery, entrega é indisponível.
    3. Se existem DeliveryZone ativas, o endereço PRECISA corresponder
       a uma delas. Não existe fallback para a taxa padrão nesse caso.
    4. A comparação de cidade/bairro ignora caixa, acentos e espaços extras.
    5. A taxa padrão do tenant só é fallback quando a loja não possui
       nenhuma DeliveryZone ativa.
    """

    if delivery_type == "pickup":
        return {
            "available": True,
            "found": True,
            "fee": ZERO,
            "fee_display": "Retirada na loja",
            "message": "",
            "source": "pickup",
            "zone": None,
        }

    if not getattr(tenant, "accepts_delivery", False):
        return {
            "available": False,
            "found": False,
            "fee": ZERO,
            "fee_display": "—",
            "message": "Esta loja não aceita pedidos para entrega.",
            "source": "delivery_disabled",
            "zone": None,
        }

    normalized_city = normalize_location_text(city)
    normalized_neighborhood = normalize_location_text(neighborhood)

    if not normalized_city or not normalized_neighborhood:
        return {
            "available": False,
            "found": False,
            "fee": ZERO,
            "fee_display": "—",
            "message": "Informe cidade e bairro para confirmar a entrega.",
            "source": "address_required",
            "zone": None,
        }

    active_zones = list(
        DeliveryZone.objects
        .filter(
            tenant=tenant,
            is_active=True,
        )
        .only(
            "id",
            "city",
            "neighborhood",
            "fee",
        )
        .order_by(
            "city",
            "neighborhood",
        )
    )

    if active_zones:
        for zone in active_zones:
            zone_city = normalize_location_text(zone.city)
            zone_neighborhood = normalize_location_text(zone.neighborhood)

            if (
                zone_city == normalized_city
                and zone_neighborhood == normalized_neighborhood
            ):
                fee = _to_decimal(zone.fee).quantize(Decimal("0.01"))

                return {
                    "available": True,
                    "found": True,
                    "fee": fee,
                    "fee_display": format_delivery_fee(fee),
                    "message": "Endereço atendido pela área de entrega da loja.",
                    "source": "delivery_zone",
                    "zone": zone,
                }

        return {
            "available": False,
            "found": False,
            "fee": ZERO,
            "fee_display": "—",
            "message": (
                "Esta loja não entrega no bairro informado. "
                "Confira o endereço ou escolha retirada, se disponível."
            ),
            "source": "not_served",
            "zone": None,
        }

    # Compatibilidade com lojas antigas que ainda não cadastraram zonas.
    fallback = _to_decimal(
        getattr(tenant, "delivery_fee", None)
    ).quantize(Decimal("0.01"))

    return {
        "available": True,
        "found": False,
        "fee": fallback,
        "fee_display": format_delivery_fee(fallback),
        "message": (
            "Taxa padrão da loja aplicada."
            if fallback > ZERO
            else "Entrega disponível sem taxa cadastrada."
        ),
        "source": "tenant_default",
        "zone": None,
    }


def delivery_result_to_json(result):
    """
    Converte resolve_delivery() para resposta JSON mantendo compatibilidade
    com os frontends atuais que já usam found, fee e fee_display.
    """
    return {
        "available": bool(result["available"]),
        "found": bool(result["found"]),
        "fee": str(
            _to_decimal(result["fee"]).quantize(Decimal("0.01"))
        ),
        "fee_display": result["fee_display"],
        "message": result["message"],
        "source": result["source"],
    }
