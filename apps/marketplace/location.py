SESSION_KEY = "vemdedelivery_delivery_location"


def _clean(value):
    return str(value or "").strip()


def _clean_state(value):
    return _clean(value).upper()[:2]


def serialize_customer_address(address):
    return {
        "source": "saved",
        "customer_address_id": address.pk,
        "label": _clean(address.label) or "Endereço salvo",
        "zip_code": _clean(address.zip_code),
        "street": _clean(address.street),
        "number": _clean(address.number),
        "complement": _clean(address.complement),
        "neighborhood": _clean(address.neighborhood),
        "city": _clean(address.city),
        "state": _clean_state(address.state),
        "reference": _clean(address.reference),
    }


def serialize_manual_address(data):
    return {
        "source": "manual",
        "customer_address_id": None,
        "label": _clean(data.get("label")) or "Endereço informado",
        "zip_code": _clean(data.get("zip_code") or data.get("cep")),
        "street": _clean(data.get("street") or data.get("address")),
        "number": _clean(data.get("number")),
        "complement": _clean(data.get("complement")),
        "neighborhood": _clean(data.get("neighborhood")),
        "city": _clean(data.get("city")),
        "state": _clean_state(data.get("state")),
        "reference": _clean(data.get("reference")),
    }


def is_valid_delivery_location(location):
    return bool(
        isinstance(location, dict)
        and _clean(location.get("city"))
        and _clean(location.get("neighborhood"))
    )


def get_global_delivery_location(request):
    location = request.session.get(SESSION_KEY)

    if not is_valid_delivery_location(location):
        return None

    if (
        location.get("source") == "saved"
        and location.get("customer_address_id")
    ):
        if not request.user.is_authenticated:
            clear_global_delivery_location(request)
            return None

        try:
            customer = request.user.customer_profile
        except Exception:
            clear_global_delivery_location(request)
            return None

        address = (
            customer.addresses
            .filter(
                pk=location["customer_address_id"]
            )
            .first()
        )

        if address is None:
            clear_global_delivery_location(request)
            return None

        refreshed = serialize_customer_address(address)

        if refreshed != location:
            request.session[SESSION_KEY] = refreshed
            request.session.modified = True

        return refreshed

    return location


def set_global_delivery_location(request, location):
    if not is_valid_delivery_location(location):
        raise ValueError("Cidade e bairro são obrigatórios.")

    request.session[SESSION_KEY] = location
    request.session.modified = True

    return location


def clear_global_delivery_location(request):
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True


def delivery_location_short_label(location):
    if not location:
        return ""

    parts = []

    if location.get("label"):
        parts.append(_clean(location["label"]))

    neighborhood = _clean(location.get("neighborhood"))
    city = _clean(location.get("city"))
    state = _clean_state(location.get("state"))

    region = ""

    if neighborhood:
        region = neighborhood

    if city:
        region += (", " if region else "") + city

    if state:
        region += f"/{state}"

    if region:
        parts.append(region)

    return " · ".join(parts)
