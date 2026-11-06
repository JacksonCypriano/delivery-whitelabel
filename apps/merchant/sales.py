from django.utils import timezone
from rest_framework.response import Response
from .api import MerchantAPI
from apps.orders.models import SalesSettings, SalesMessage, OrderFeedback

BOOLS = (
    "scheduling_enabled",
    "recovery_enabled",
    "feedback_enabled",
    "reactivation_enabled",
)
LIMITS = {
    "lead_minutes": (15, 1440),
    "horizon_days": (1, 30),
    "recovery_minutes": (30, 10080),
    "feedback_minutes": (15, 10080),
    "inactive_days": (7, 365),
}


class Sales(MerchantAPI):
    def get(self, request):
        cfg, _ = SalesSettings.objects.get_or_create(tenant=request.tenant)
        from .pagination import paginate, metadata
        messages = paginate(SalesMessage.objects.filter(tenant=request.tenant).order_by("-created_at", "-pk").values("id", "kind", "text", "created_at", "attempted_at", "sent_at", "error", "converted_at", "skipped_at"), request, "messages_page")
        feedback = paginate(OrderFeedback.objects.filter(tenant=request.tenant).order_by("-created_at", "-pk").values("id", "order_id", "rating", "comment", "handled_at"), request, "feedback_page")
        return Response({"settings": {k: getattr(cfg,k) for k in (*BOOLS,*LIMITS)}, "messages": list(messages), "feedback": list(feedback), "messages_pagination": metadata(messages), "feedback_pagination": metadata(feedback)})

    def post(self, request):
        cfg, _ = SalesSettings.objects.get_or_create(tenant=request.tenant)
        if "handled_id" in request.data:
            count = OrderFeedback.objects.filter(
                tenant=request.tenant, pk=request.data["handled_id"]
            ).update(handled_at=timezone.now())
            return Response(
                {"detail": "Avaliação tratada."}, status=200 if count else 404
            )
        updates = {}
        for key, val in request.data.items():
            if key in BOOLS:
                if not isinstance(val, bool):
                    return Response({"detail": "Opção inválida."}, status=400)
            elif key in LIMITS:
                if (
                    isinstance(val, bool)
                    or not isinstance(val, int)
                    or not LIMITS[key][0] <= val <= LIMITS[key][1]
                ):
                    return Response({"detail": f"Valor inválido: {key}."}, status=400)
            else:
                return Response({"detail": "Configuração desconhecida."}, status=400)
            updates[key] = val
        SalesSettings.objects.filter(pk=cfg.pk).update(**updates)
        return self.get(request)
