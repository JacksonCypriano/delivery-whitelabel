import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import AsaasFeeSnapshot
from .provider import Asaas, BillingError, environment


def _decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise BillingError("O Asaas retornou uma tarifa em formato inválido.") from exc


def _datetime(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        try:
            parsed = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise BillingError("O Asaas retornou uma data de promoção inválida.") from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _discount_is_valid(expiration, now):
    return bool(expiration and expiration > now)


def parse_asaas_fees(payload, *, now=None):
    """Normalize the relevant /myAccount/fees response.

    The returned structure keeps standard and promotional values separately and
    exposes the effective values for the current instant. Missing administrative
    blocks are accepted because subaccounts do not necessarily expose every fee
    available in the parent account.
    """
    if not isinstance(payload, dict):
        raise BillingError("O Asaas retornou uma resposta de tarifas inválida.")

    now = now or timezone.now()
    payment = payload.get("payment") if isinstance(payload.get("payment"), dict) else {}

    pix_raw = payment.get("pix") if isinstance(payment.get("pix"), dict) else {}
    pix_expiration = _datetime(pix_raw.get("discountExpiration"))
    pix_standard = _decimal(pix_raw.get("fixedFeeValue"))
    pix_discount = _decimal(pix_raw.get("fixedFeeValueWithDiscount"))
    pix_effective = (
        pix_discount
        if pix_discount is not None and _discount_is_valid(pix_expiration, now)
        else pix_standard
    )

    boleto_raw = payment.get("bankSlip") if isinstance(payment.get("bankSlip"), dict) else {}
    boleto_expiration = _datetime(boleto_raw.get("expirationDate"))
    boleto_standard = _decimal(boleto_raw.get("defaultValue"))
    boleto_discount = _decimal(boleto_raw.get("discountValue"))
    boleto_effective = (
        boleto_discount
        if boleto_discount is not None and _discount_is_valid(boleto_expiration, now)
        else boleto_standard
    )

    card_raw = payment.get("creditCard") if isinstance(payment.get("creditCard"), dict) else {}
    card_expiration = _datetime(card_raw.get("discountExpiration"))
    card_discount_valid = bool(card_raw.get("hasValidDiscount")) and _discount_is_valid(
        card_expiration, now
    )
    card_fixed = _decimal(card_raw.get("operationValue"))
    standard_rates = {
        "1": _decimal(card_raw.get("oneInstallmentPercentage")),
        "2_6": _decimal(card_raw.get("upToSixInstallmentsPercentage")),
        "7_12": _decimal(card_raw.get("upToTwelveInstallmentsPercentage")),
        "13_21": _decimal(card_raw.get("upToTwentyOneInstallmentsPercentage")),
    }
    discount_rates = {
        "1": _decimal(card_raw.get("discountOneInstallmentPercentage")),
        "2_6": _decimal(card_raw.get("discountUpToSixInstallmentsPercentage")),
        "7_12": _decimal(card_raw.get("discountUpToTwelveInstallmentsPercentage")),
        "13_21": _decimal(card_raw.get("discountUpToTwentyOneInstallmentsPercentage")),
    }
    effective_rates = {
        key: (
            discount_rates[key]
            if card_discount_valid and discount_rates[key] is not None
            else standard_rates[key]
        )
        for key in standard_rates
    }

    invoice_raw = payload.get("invoice") if isinstance(payload.get("invoice"), dict) else {}
    child_raw = payload.get("childAccount") if isinstance(payload.get("childAccount"), dict) else {}

    expirations = [
        value
        for value in (pix_expiration, boleto_expiration, card_expiration)
        if value is not None and value > now
    ]

    return {
        "pix": {
            "standard": pix_standard,
            "discount": pix_discount,
            "effective": pix_effective,
            "discount_expires_at": pix_expiration,
            "monthly_free": pix_raw.get("monthlyCreditsWithoutFee"),
        },
        "boleto": {
            "standard": boleto_standard,
            "discount": boleto_discount,
            "effective": boleto_effective,
            "discount_expires_at": boleto_expiration,
            "days_to_receive": boleto_raw.get("daysToReceive"),
        },
        "card": {
            "fixed": card_fixed,
            "standard": standard_rates,
            "discount": discount_rates,
            "effective": effective_rates,
            "discount_expires_at": card_expiration,
            "days_to_receive": card_raw.get("daysToReceive"),
        },
        "invoice_fee": _decimal(invoice_raw.get("feeValue")),
        "child_account_fee": _decimal(child_raw.get("creationFeeValue")),
        "next_discount_expiration": min(expirations) if expirations else None,
    }


def _fingerprint_values(summary):
    relevant = {
        "pix": str(summary["pix"]["effective"]),
        "boleto": str(summary["boleto"]["effective"]),
        "card_fixed": str(summary["card"]["fixed"]),
        "card_1": str(summary["card"]["effective"]["1"]),
        "card_2_6": str(summary["card"]["effective"]["2_6"]),
        "card_7_12": str(summary["card"]["effective"]["7_12"]),
        "card_13_21": str(summary["card"]["effective"]["13_21"]),
        "invoice": str(summary["invoice_fee"]),
        "child_account": str(summary["child_account_fee"]),
        "discount_expiration": (
            summary["next_discount_expiration"].isoformat()
            if summary["next_discount_expiration"]
            else None
        ),
    }
    encoded = json.dumps(relevant, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sync_platform_fee_snapshot(*, api=None, now=None):
    """Fetch platform fees and persist a row only when relevant terms changed."""
    api = api or Asaas()
    now = now or timezone.now()
    payload = api.request("GET", "/myAccount/fees/")
    summary = parse_asaas_fees(payload, now=now)

    # Platform monitoring requires the fields that affect VemDeDelivery costs.
    required = (
        summary["pix"]["effective"],
        summary["card"]["fixed"],
        summary["card"]["effective"]["1"],
        summary["invoice_fee"],
        summary["child_account_fee"],
    )
    if any(value is None for value in required):
        raise BillingError("O Asaas não retornou todas as tarifas necessárias da conta principal.")

    fingerprint = _fingerprint_values(summary)
    previous = AsaasFeeSnapshot.current(environment())
    if previous and previous.fingerprint == fingerprint:
        return previous, False, summary

    snapshot = AsaasFeeSnapshot.objects.create(
        environment=environment(),
        fingerprint=fingerprint,
        payload=payload,
        pix_fee=summary["pix"]["effective"],
        boleto_fee=summary["boleto"]["effective"],
        card_fixed_fee=summary["card"]["fixed"],
        card_1x_percent=summary["card"]["effective"]["1"],
        card_2_6_percent=summary["card"]["effective"]["2_6"],
        card_7_12_percent=summary["card"]["effective"]["7_12"],
        card_13_21_percent=summary["card"]["effective"]["13_21"],
        nfse_fee=summary["invoice_fee"],
        child_account_fee=summary["child_account_fee"],
        discount_expires_at=summary["next_discount_expiration"],
    )
    return snapshot, True, summary


def current_platform_fee_snapshot():
    return AsaasFeeSnapshot.current(environment())


def card_price_preserving_pix(value, policy):
    """Gross-up card 1x so its net is approximately the same as Pix.

    Production never relies on manually copied fee values. The stored Asaas
    payload is re-evaluated at quote time, so a known promotion expiration takes
    effect immediately even before the next daily synchronization.
    """
    value = Decimal(value)
    snapshot = current_platform_fee_snapshot()
    if snapshot:
        if (
            environment() == "production"
            and snapshot.observed_at < timezone.now() - timedelta(hours=48)
        ):
            raise BillingError(
                "As taxas do cartão estão aguardando uma atualização do Asaas. "
                "Tente novamente mais tarde."
            )
        summary = parse_asaas_fees(snapshot.payload)
        pix_fee = summary["pix"]["effective"]
        card_fixed = summary["card"]["fixed"]
        card_percent = summary["card"]["effective"]["1"]
        if any(value is None for value in (pix_fee, card_fixed, card_percent)):
            raise BillingError("O Asaas não informou todas as taxas necessárias do cartão.")
    elif environment() == "production":
        raise BillingError(
            "As taxas do cartão ainda não foram sincronizadas com o Asaas. "
            "Tente novamente mais tarde."
        )
    else:
        # Sandbox/test compatibility before the first fee snapshot.
        pix_fee = policy.fixed_pix_fee
        card_fixed = policy.card_fixed_fee
        card_percent = policy.card_percent

    divisor = Decimal("1") - (Decimal(card_percent) / Decimal("100"))
    if divisor <= 0:
        raise BillingError("A taxa de cartão cadastrada é inválida.")
    gross = max(value, (value - Decimal(pix_fee) + Decimal(card_fixed)) / divisor)
    return gross.quantize(Decimal(".01"), rounding=ROUND_CEILING)
