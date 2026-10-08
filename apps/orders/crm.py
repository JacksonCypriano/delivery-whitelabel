from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Count, Max
from django.utils import timezone
from celery import shared_task
from apps.customers.models import Customer
from apps.coupons.models import CouponCampaign, CouponAssignment
from .models import (
    Order,
    OrderItem,
    LoyaltyEntry,
    LoyaltySettings,
    CustomerProfile,
    CustomerCampaign,
    SalesMessage,
    SalesSettings,
)
from .operations import operational_order_q


def customers(tenant, page_request=None):
    ids = (
        Order.objects.filter(tenant=tenant, customer__isnull=False)
        .filter(operational_order_q())
        .values("customer_id")
    )
    queryset = Customer.objects.filter(pk__in=ids).select_related("user").order_by("pk")
    page = None
    if page_request is not None:
        from django.db.models import Q, F
        from apps.merchant.pagination import paginate
        delivered = Q(orders__tenant=tenant, orders__status="delivered")
        queryset = queryset.annotate(purchase_count=Count("orders", filter=delivered), purchase_total=Sum("orders__total", filter=delivered), last_purchase=Max("orders__created_at", filter=delivered))
        segment = page_request.GET.get("segment", "")
        filters = {"new": Q(purchase_count__lte=1), "recurring": Q(purchase_count__gte=2), "frequent": Q(purchase_count__gte=5), "vip": Q(purchase_total__gte=1000), "high_ticket": Q(purchase_count__gt=0, purchase_total__gte=F("purchase_count") * 100), "inactive": Q(last_purchase__lt=timezone.now()-timedelta(days=30)), "birthday": Q(pk__in=CustomerProfile.objects.filter(tenant=tenant, birthday__month=timezone.localdate().month).values("customer_id"))}
        if segment in filters:
            queryset = queryset.filter(filters[segment])
        page = paginate(queryset, page_request)
        queryset = page
    result = []
    for customer in queryset:
        orders = Order.objects.filter(
            tenant=tenant, customer=customer, status="delivered"
        )
        stats = orders.aggregate(
            count=Count("id"), spent=Sum("total"), last=Max("created_at")
        )
        spent = stats["spent"] or Decimal(0)
        count = stats["count"]
        last = stats["last"]
        segments = []
        if count <= 1:
            segments.append("new")
        if count >= 2:
            segments.append("recurring")
        if spent >= 1000:
            segments.append("vip")
        if count >= 5:
            segments.append("frequent")
        if count and spent / count >= 100:
            segments.append("high_ticket")
        if last and last < timezone.now() - timedelta(days=30):
            segments.append("inactive")
        profile = CustomerProfile.objects.filter(
            tenant=tenant, customer=customer
        ).first()
        if (
            profile
            and profile.birthday
            and profile.birthday.month == timezone.localdate().month
        ):
            segments.append("birthday")
        balance = (
            LoyaltyEntry.objects.filter(tenant=tenant, customer=customer).aggregate(
                n=Sum("points")
            )["n"]
            or 0
        )
        result.append(
            {
                "id": customer.pk,
                "name": customer.user.get_full_name() or customer.user.username,
                "phone": customer.phone,
                "count": count,
                "spent": str(spent),
                "average": str(
                    (spent / count).quantize(Decimal(".01")) if count else 0
                ),
                "last": last,
                "segments": segments,
                "points": balance,
                "products": list(
                    OrderItem.objects.filter(order__in=orders)
                    .values("name")
                    .annotate(quantity=Sum("quantity"))
                    .order_by("-quantity")[:5]
                ),
                "orders": list(
                    orders.order_by("-created_at").values(
                        "id",
                        "total",
                        "created_at",
                        "coupon_code",
                        "source",
                        "attribution",
                    )[:20]
                ),
                "feedback": list(
                    customer.orders.filter(
                        tenant=tenant, orderfeedback__isnull=False
                    ).values("id", "orderfeedback__rating", "orderfeedback__comment")[
                        :20
                    ]
                ),
                "birthday": profile.birthday if profile else None,
                "notes": profile.notes if profile else "",
            }
        )
    return (result, page) if page_request is not None else result


@shared_task
def accrue_loyalty():
    for cfg in LoyaltySettings.objects.filter(enabled=True, tenant__is_active=True):
        for order in Order.objects.filter(
            tenant=cfg.tenant,
            customer__isnull=False,
            status="delivered",
            created_at__gte=cfg.enabled_at,
        ).select_related("customer"):
            if order.payment_flow == "online":
                from apps.merchant.orders import _payment_info

                checkout = getattr(order, "whatsappcheckout", None)
                if not _payment_info(order, checkout)["paid"]:
                    continue
            points = (
                int(order.total / cfg.reais_per_point) if cfg.reais_per_point > 0 else 0
            )
            if points > 0:
                LoyaltyEntry.objects.get_or_create(
                    tenant=cfg.tenant,
                    key=f"order:{order.pk}",
                    defaults={
                        "customer": order.customer,
                        "order": order,
                        "points": points,
                    },
                )


@transaction.atomic
def redeem(tenant, customer_id, key):
    cfg = (
        LoyaltySettings.objects.select_for_update()
        .filter(tenant=tenant, enabled=True)
        .first()
    )
    if not cfg:
        raise ValueError("Fidelidade desativada.")
    existing = LoyaltyEntry.objects.filter(tenant=tenant, key="redeem:" + key).first()
    if existing:
        if existing.customer_id != customer_id:
            raise ValueError("Referência já utilizada.")
        return existing.campaign
    if not Order.objects.filter(
        tenant=tenant, customer_id=customer_id, status="delivered"
    ).exists():
        raise ValueError("Cliente não encontrado nesta loja.")
    balance = (
        LoyaltyEntry.objects.filter(tenant=tenant, customer_id=customer_id).aggregate(
            n=Sum("points")
        )["n"]
        or 0
    )
    if cfg.reward_points < 1 or balance < cfg.reward_points:
        raise ValueError("Pontos insuficientes.")
    import secrets

    coupon = CouponCampaign.objects.create(
        tenant=tenant,
        name="Benefício fidelidade",
        code="FID" + secrets.token_hex(8).upper(),
        discount_type="fixed_amount",
        discount_value=cfg.reward_value,
        audience_type="specific",
        usage_limit=1,
        usage_limit_per_customer=1,
    )
    CouponAssignment.objects.create(campaign=coupon, customer_id=customer_id)
    LoyaltyEntry.objects.create(
        tenant=tenant,
        customer_id=customer_id,
        key="redeem:" + key,
        points=-cfg.reward_points,
        campaign=coupon,
    )
    return coupon


@shared_task
def plan_customer_campaigns():
    from .sales import eligible_customer

    for campaign in CustomerCampaign.objects.filter(
        active=True, tenant__is_active=True
    ):
        audience = [
            c["id"]
            for c in customers(campaign.tenant)
            if campaign.segment in c["segments"]
        ]
        for customer in Customer.objects.filter(pk__in=audience):
            if eligible_customer(campaign.tenant, customer):
                SalesMessage.objects.get_or_create(
                    tenant=campaign.tenant,
                    key=f"campaign:{campaign.pk}:{customer.pk}",
                    defaults={
                        "customer": customer,
                        "campaign": campaign,
                        "kind": "campaign",
                    },
                )
