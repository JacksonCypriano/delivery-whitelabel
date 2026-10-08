from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID
from django.db.models import Count
from django.utils import timezone
from rest_framework.response import Response
from .api import MerchantAPI
from apps.orders.crm import customers, redeem
from apps.orders.models import (
    LoyaltySettings,
    CustomerProfile,
    CustomerCampaign,
    FunnelEvent,
    Order,
    SalesMessage,
)


class CRM(MerchantAPI):
    def get(self, request):
        cfg, _ = LoyaltySettings.objects.get_or_create(tenant=request.tenant)
        from .pagination import paginate, metadata
        customer_rows, customer_page = customers(request.tenant, request)
        campaign_page = paginate(CustomerCampaign.objects.filter(tenant=request.tenant).order_by("-pk"), request, "campaigns_page")
        campaigns = []
        for c in campaign_page:
            notices = SalesMessage.objects.filter(tenant=request.tenant, campaign=c)
            campaigns.append(
                {
                    "id": c.pk,
                    "name": c.name,
                    "text": c.text,
                    "segment": c.segment,
                    "active": c.active,
                    "sent": notices.filter(sent_at__isnull=False).count(),
                    "converted": notices.filter(converted_at__isnull=False).count(),
                }
            )
        from apps.orders.operations import operational_order_q

        operational = Order.objects.filter(
            tenant=request.tenant, abandoned_at__isnull=True
        ).filter(operational_order_q())
        from apps.billing.models import OrderPayment
        from apps.integrations.models import WhatsAppCheckout

        paid = set(
            OrderPayment.objects.filter(
                tenant=request.tenant, status="PAID"
            ).values_list("order_id", flat=True)
        )
        paid.update(
            WhatsAppCheckout.objects.filter(
                cart__tenant=request.tenant,
                paid_at__isnull=False,
                order_id__isnull=False,
            ).values_list("order_id", flat=True)
        )
        return Response(
            {
                "order_count": operational.count(),
                "paid_count": operational.filter(pk__in=paid).count(),
                "customers": customer_rows,
                "customers_pagination": metadata(customer_page),
                "campaigns_pagination": metadata(campaign_page),
                "loyalty": {
                    "enabled": cfg.enabled,
                    "reais_per_point": str(cfg.reais_per_point),
                    "reward_points": cfg.reward_points,
                    "reward_value": str(cfg.reward_value),
                },
                "campaigns": campaigns,
                "funnel": list(
                    FunnelEvent.objects.filter(tenant=request.tenant)
                    .values("stage")
                    .annotate(total=Count("id"))
                ),
                "origins": list(
                    operational.values("source").annotate(total=Count("id"))
                ),
            }
        )

    def post(self, request):
        data = request.data
        action = data.get("action")
        try:
            if action == "loyalty":
                enabled = data.get("enabled")
                amount = Decimal(str(data.get("reais_per_point")))
                reward = Decimal(str(data.get("reward_value")))
                points = data.get("reward_points")
                if (
                    not isinstance(enabled, bool)
                    or not amount.is_finite()
                    or not reward.is_finite()
                    or not Decimal(".01") <= amount <= 10000
                    or not Decimal(".01") <= reward <= 1000
                    or isinstance(points, bool)
                    or not isinstance(points, int)
                    or not 1 <= points <= 100000
                ):
                    raise ValueError("Configuração de fidelidade inválida.")
                cfg, _ = LoyaltySettings.objects.get_or_create(tenant=request.tenant)
                if enabled and not cfg.enabled:
                    cfg.enabled_at = timezone.now()
                cfg.enabled = enabled
                cfg.reais_per_point = amount
                cfg.reward_points = points
                cfg.reward_value = reward
                cfg.save()
            elif action == "redeem":
                key = str(UUID(str(data.get("key"))))
                coupon = redeem(request.tenant, int(data.get("customer")), key)
                return Response({"code": coupon.code})
            elif action == "profile":
                customer_id = int(data.get("customer"))
                if not Order.objects.filter(
                    tenant=request.tenant, customer_id=customer_id
                ).exists():
                    raise ValueError("Cliente não encontrado.")
                birthday = (
                    date.fromisoformat(data["birthday"])
                    if data.get("birthday")
                    else None
                )
                notes = str(data.get("notes", ""))
                if len(notes) > 1000:
                    raise ValueError("Observação muito longa.")
                CustomerProfile.objects.update_or_create(
                    tenant=request.tenant,
                    customer_id=customer_id,
                    defaults={"birthday": birthday, "notes": notes},
                )
            elif action == "campaign":
                name = str(data.get("name", "")).strip()
                text = str(data.get("text", "")).strip()
                segment = data.get("segment")
                if (
                    segment
                    not in (
                        "new",
                        "recurring",
                        "vip",
                        "frequent",
                        "high_ticket",
                        "inactive",
                        "birthday",
                    )
                    or not 1 <= len(name) <= 120
                    or not 1 <= len(text) <= 1000
                ):
                    raise ValueError("Confira nome, segmento e mensagem.")
                CustomerCampaign.objects.create(
                    tenant=request.tenant, name=name, text=text, segment=segment
                )
            elif action == "campaign_toggle":
                if not isinstance(data.get("active"), bool):
                    raise ValueError("Ativação inválida.")
                if not CustomerCampaign.objects.filter(
                    tenant=request.tenant, pk=data.get("id")
                ).update(active=data["active"]):
                    return Response({"detail": "Campanha não encontrada."}, status=404)
            else:
                raise ValueError("Ação inválida.")
        except (ValueError, TypeError, InvalidOperation) as exc:
            return Response({"detail": str(exc) or "Dados inválidos."}, status=400)
        return self.get(request)
