# apps/tenants/views.py

from decimal import Decimal

from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import DeliveryZone
from .serializers import TenantCreateSerializer


@api_view(["POST"])
def create_tenant(request):
    serializer = TenantCreateSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST,
    )


def delivery_fee_api(request):
    """
    GET /api/delivery-fee/?city=Cidade&neighborhood=Bairro

    Retorna a taxa de entrega para o tenant atual.
    """

    tenant = getattr(request, "tenant", None)

    if not tenant:
        return JsonResponse(
            {
                "found": False,
                "fee": "0.00",
                "fee_display": "—",
                "message": "Loja não identificada.",
            },
            status=400,
        )


    city = (
        request.GET.get("city", "")
        .strip()
    )

    neighborhood = (
        request.GET.get("neighborhood", "")
        .strip()
    )


    if not city or not neighborhood:
        return JsonResponse(
            {
                "found": False,
                "fee": "0.00",
                "fee_display": "—",
                "message": "Informe cidade e bairro.",
            },
            status=400,
        )


    zone = (
        DeliveryZone.objects
        .filter(
            tenant=tenant,
            city__iexact=city,
            neighborhood__iexact=neighborhood,
            is_active=True,
        )
        .first()
    )


    if zone:

        fee = zone.fee or Decimal("0.00")

        if fee > 0:

            fee_display = (
                f"R$ {fee:.2f}"
                .replace(".", ",")
            )

        else:

            fee_display = "Grátis"


        return JsonResponse(
            {
                "found": True,
                "fee": str(fee),
                "fee_display": fee_display,
                "message": "",
            }
        )


    # ------------------------------------------------------------
    # Se existem zonas cadastradas, não assume automaticamente
    # que qualquer bairro deve usar a taxa padrão.
    # ------------------------------------------------------------

    has_delivery_zones = DeliveryZone.objects.filter(
        tenant=tenant,
        is_active=True,
    ).exists()


    if has_delivery_zones:

        return JsonResponse(
            {
                "found": False,
                "fee": "0.00",
                "fee_display": "Não atendido",
                "message": (
                    "Este bairro não está cadastrado "
                    "nas áreas de entrega."
                ),
            }
        )


    # ------------------------------------------------------------
    # Se a loja não configurou zonas, usa a taxa padrão.
    # ------------------------------------------------------------

    fallback = (
        tenant.delivery_fee
        or Decimal("0.00")
    )


    if fallback > 0:

        fee_display = (
            f"R$ {fallback:.2f}"
            .replace(".", ",")
            + " (padrão)"
        )

        return JsonResponse(
            {
                "found": False,
                "fee": str(fallback),
                "fee_display": fee_display,
                "message": (
                    "Taxa padrão de entrega aplicada."
                ),
            }
        )


    return JsonResponse(
        {
            "found": False,
            "fee": "0.00",
            "fee_display": "Grátis",
            "message": "Entrega grátis.",
        }
    )
