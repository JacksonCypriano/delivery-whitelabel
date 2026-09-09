from __future__ import annotations

import re


def normalize_br_phone(value) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return None

    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("55"):
        national = digits[2:]
    else:
        national = digits

    # Aceita fixo (10 dígitos) e celular (11 dígitos) com DDD.
    if len(national) not in (10, 11):
        return None
    if national[0] == "0" or national[:2] == "00":
        return None

    return f"55{national}"
