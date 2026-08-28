from apps.tenants.delivery import resolve_delivery

from .location import (
    delivery_location_short_label,
    get_global_delivery_location,
)


class GlobalDeliveryLocationMiddleware:
    """
    Expõe o endereço global e a situação de entrega em qualquer subdomínio.

    Requer:
    - SessionMiddleware antes deste middleware;
    - TenantMiddleware antes deste middleware para que request.tenant exista.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        location = get_global_delivery_location(request)

        request.global_delivery_location = location
        request.global_delivery_location_label = (
            delivery_location_short_label(location)
        )
        request.global_delivery_result = None

        tenant = getattr(request, "tenant", None)

        if tenant and location:
            request.global_delivery_result = resolve_delivery(
                tenant=tenant,
                delivery_type="delivery",
                city=location.get("city", ""),
                neighborhood=location.get("neighborhood", ""),
            )

        return self.get_response(request)
