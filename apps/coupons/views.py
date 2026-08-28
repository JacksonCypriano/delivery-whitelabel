import json
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.customers.models import Customer

from .services import validate_coupon


def to_decimal(value, default="0.00"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


@require_POST
def validate_coupon_api(request):
    tenant = getattr(request, "tenant", None)

    if tenant is None:
        return JsonResponse(
            {
                "valid": False,
                "message": "Loja não identificada.",
            },
            status=400,
        )

    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "valid": False,
                "message": "Entre na sua conta para usar cupons.",
            },
            status=401,
        )

    customer = (
        Customer.objects
        .filter(user=request.user)
        .first()
    )

    if customer is None:
        return JsonResponse(
            {
                "valid": False,
                "message": "Cadastro de cliente não encontrado.",
            },
            status=400,
        )

    try:
        data = json.loads(
            request.body.decode("utf-8") or "{}"
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {
                "valid": False,
                "message": "Dados inválidos.",
            },
            status=400,
        )

    code = (
        data.get("code")
        or ""
    ).strip()

    if not code:
        return JsonResponse(
            {
                "valid": False,
                "message": "Informe um cupom.",
            },
            status=400,
        )

    # Estes valores servem somente para a prévia visual.
    # O checkout fará a validação definitiva no servidor
    # antes de criar o pedido.
    subtotal = to_decimal(
        data.get("subtotal")
    )

    delivery_fee = to_decimal(
        data.get("delivery_fee")
    )

    result = validate_coupon(
        code=code,
        tenant=tenant,
        customer=customer,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
    )

    if not result["valid"]:
        return JsonResponse(
            {
                "valid": False,
                "message": result["message"],
            },
            status=400,
        )

    campaign = result["campaign"]

    return JsonResponse(
        {
            "valid": True,
            "code": campaign.code,
            "message": result["message"],
            "discount": str(
                result["discount"].quantize(
                    Decimal("0.01")
                )
            ),
            "final_total": str(
                result["final_total"].quantize(
                    Decimal("0.01")
                )
            ),
        }
    )
