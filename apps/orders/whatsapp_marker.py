import re

from django.core import signing


ORDER_MARKER_PREFIX = "VDD-ORDER:"
ORDER_MARKER_SALT = "vemdedelivery.whatsapp-order.v1"
ORDER_MARKER_RE = re.compile(r"VDD-ORDER:(\d+:[A-Za-z0-9_-]+)")


def build_order_marker(order):
    """Return a compact tamper-evident marker for a generated WhatsApp order."""
    signed = signing.Signer(salt=ORDER_MARKER_SALT).sign(str(order.pk))
    return f"{ORDER_MARKER_PREFIX}{signed}"


def extract_order_id(text):
    """Validate a marker found in customer text and return its order id.

    Package 11.0.0 rendered the reference line in WhatsApp italics. Because
    ``_`` is also valid in Django's URL-safe signature alphabet, the closing
    markdown underscore could be consumed by the regex and invalidate an
    otherwise authentic marker. New messages are emitted without markdown,
    while the one-character fallback below keeps already-generated 11.0.0
    messages valid without weakening the signature check.
    """
    match = ORDER_MARKER_RE.search(text or "")
    if not match:
        return None

    signed_value = match.group(1)
    candidates = [signed_value]
    if signed_value.endswith("_"):
        candidates.append(signed_value[:-1])

    signer = signing.Signer(salt=ORDER_MARKER_SALT)
    for candidate in candidates:
        try:
            raw = signer.unsign(candidate)
            order_id = int(raw)
        except (signing.BadSignature, TypeError, ValueError):
            continue
        return order_id if order_id > 0 else None
    return None
