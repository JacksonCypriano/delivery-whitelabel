"""Normalização e validação dos campos usados na criação de subcontas Asaas.

Mantém a interface amigável (máscaras brasileiras) sem enviar pontuação ou
código de país quando o endpoint espera apenas DDD + número.
"""
import re


COMPANY_TYPE_CHOICES = (
    ("", "Selecione o tipo da empresa"),
    ("MEI", "MEI — Microempreendedor Individual"),
    ("LIMITED", "Sociedade Limitada (LTDA)"),
    ("INDIVIDUAL", "Empresa Individual"),
    ("ASSOCIATION", "Associação"),
)
COMPANY_TYPES = {value for value, _label in COMPANY_TYPE_CHOICES if value}


def clean_document(value):
    """Return CPF/CNPJ in the provider representation (no punctuation).

    Numeric CPF/CNPJ receive local check-digit validation. Alphanumeric CNPJ
    remains supported structurally because the project already anticipates the
    national alphanumeric CNPJ transition.
    """
    raw = re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()
    if len(raw) == 11 and raw.isdigit():
        if not _valid_cpf(raw):
            raise ValueError("CPF inválido. Confira os 11 dígitos do documento.")
        return raw

    if len(raw) == 14:
        if not re.fullmatch(r"[A-Z0-9]{12}\d{2}", raw):
            raise ValueError("CNPJ inválido. Informe o CNPJ completo.")
        if raw.isdigit() and not _valid_cnpj(raw):
            raise ValueError("CNPJ inválido. Confira os 14 dígitos do documento.")
        return raw

    raise ValueError("Informe um CPF com 11 dígitos ou um CNPJ com 14 caracteres.")


def document_kind(value):
    raw = re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()
    if len(raw) == 11 and raw.isdigit():
        return "CPF"
    if len(raw) == 14:
        return "CNPJ"
    return ""


def normalize_brazilian_phone(value, *, required=False, mobile=False):
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        if required:
            raise ValueError("Informe o celular com DDD.")
        return ""

    # O cadastro da loja usa E.164 brasileiro (55 + DDD + número), enquanto
    # o endpoint de subconta recebe DDD + número nos exemplos/referência.
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]

    if len(digits) not in (10, 11):
        label = "celular" if mobile else "telefone"
        raise ValueError(
            f"Informe o {label} com DDD, sem o código +55. Ex.: (11) 99999-9999."
        )
    return digits


def _valid_cpf(cpf):
    if len(set(cpf)) == 1:
        return False
    numbers = [int(ch) for ch in cpf]
    for index in (9, 10):
        total = sum(numbers[i] * (index + 1 - i) for i in range(index))
        check = (total * 10) % 11
        if check == 10:
            check = 0
        if numbers[index] != check:
            return False
    return True


def _valid_cnpj(cnpj):
    if len(set(cnpj)) == 1:
        return False
    numbers = [int(ch) for ch in cnpj]
    weights1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    total = sum(value * weight for value, weight in zip(numbers[:12], weights1))
    remainder = total % 11
    check1 = 0 if remainder < 2 else 11 - remainder
    if numbers[12] != check1:
        return False
    weights2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    total = sum(value * weight for value, weight in zip(numbers[:13], weights2))
    remainder = total % 11
    check2 = 0 if remainder < 2 else 11 - remainder
    return numbers[13] == check2
