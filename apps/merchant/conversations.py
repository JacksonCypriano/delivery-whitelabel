from datetime import timedelta
import uuid
from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response
from .api import MerchantAPI
from apps.integrations.models import TenantWhatsAppConversation, ConversationEntry


class Conversations(MerchantAPI):
    def get(self, request):
        from .pagination import paginate, metadata
        page = paginate(TenantWhatsAppConversation.objects.filter(tenant=request.tenant).order_by("-last_customer_message_at", "-pk"), request)
        rows = []
        for row in page:
            rows.append(
                {
                    "id": row.pk,
                    "phone": row.phone_number,
                    "paused": row.is_paused,
                    "reason": row.pause_reason,
                    "context": row.context,
                    "entries": list(
                        row.entries.order_by("-created_at").values(
                            "role", "text", "context", "created_at"
                        )[:30]
                    ),
                    "checkouts": list(
                        row.checkouts.order_by("-created_at").values(
                            "id", "status", "step", "order_id"
                        )[:5]
                    ),
                }
            )
        return Response({"conversations": rows, **metadata(page)})

    @transaction.atomic
    def post(self, request):
        row = (
            TenantWhatsAppConversation.objects.select_for_update()
            .filter(tenant=request.tenant, pk=request.data.get("id"))
            .first()
        )
        if not row:
            return Response({"detail": "Conversa não encontrada."}, status=404)
        action = request.data.get("action")
        if action not in ("pause", "resume"):
            return Response({"detail": "Ação inválida."}, status=400)
        # Resume does not replay old customer messages or submit a checkout.
        if action == "resume":
            row.ai_paused_until = None
            row.pause_reason = ""
        else:
            row.ai_paused_until = timezone.now() + timedelta(hours=24)
            row.pause_reason = "manual"
        row.save(update_fields=["ai_paused_until", "pause_reason", "updated_at"])
        ConversationEntry.objects.create(
            conversation=row,
            key="operator:" + str(uuid.uuid4()),
            role="operator",
            text=f"{action} por usuário #{request.user.pk}",
            context=row.context or {},
        )
        return Response({"detail": "Atendimento atualizado."})
