from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from apps.orders.models import Order

from .models import (
    AudienceType,
    CouponCampaign,
    DiscountType,
)


MONEY_PLACES = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


def get_customer_orders_for_tenant(
    customer,
    tenant,
):
    return (
        Order.objects
        .filter(
            customer=customer,
            tenant=tenant,
        )
        .exclude(
            status="cancelled",
        )
        .order_by("-created_at")
    )


def validate_campaign_period(campaign):
    now = timezone.now()

    if not campaign.is_active:
        return False, "Este cupom está inativo."

    if now < campaign.starts_at:
        return False, "Este cupom ainda não está disponível."

    if campaign.ends_at and now > campaign.ends_at:
        return False, "Este cupom expirou."

    return True, None


def validate_usage_limits(
    campaign,
    customer,
):
    if campaign.usage_limit:
        total_uses = campaign.redemptions.count()

        if total_uses >= campaign.usage_limit:
            return (
                False,
                "Este cupom atingiu o limite de utilizações.",
            )

    customer_uses = (
        campaign.redemptions
        .filter(customer=customer)
        .count()
    )

    if (
        campaign.usage_limit_per_customer
        and customer_uses >= campaign.usage_limit_per_customer
    ):
        return (
            False,
            "Você já atingiu o limite de uso deste cupom.",
        )

    return True, None


def validate_audience(
    campaign,
    customer,
):
    orders = get_customer_orders_for_tenant(
        customer,
        campaign.tenant,
    )

    audience = campaign.audience_type

    if audience == AudienceType.ALL:
        return True, None

    if audience == AudienceType.FIRST_ORDER:
        if orders.exists():
            return (
                False,
                "Este cupom é válido apenas para a primeira compra.",
            )

        return True, None

    if audience == AudienceType.NEVER_ORDERED:
        if orders.exists():
            return (
                False,
                (
                    "Este cupom é válido apenas para clientes "
                    "que nunca compraram nesta loja."
                ),
            )

        return True, None

    if audience == AudienceType.SPECIFIC:
        allowed = (
            campaign.assignments
            .filter(customer=customer)
            .exists()
        )

        if not allowed:
            return (
                False,
                "Este cupom não está disponível para sua conta.",
            )

        return True, None

    if audience == AudienceType.FREQUENT:
        order_count = orders.count()

        if (
            campaign.minimum_orders
            and order_count < campaign.minimum_orders
        ):
            return (
                False,
                (
                    "Você ainda não atingiu a quantidade mínima "
                    "de pedidos para este cupom."
                ),
            )

        if campaign.minimum_spent:
            total_spent = sum(
                (
                    order.total
                    for order in orders
                ),
                Decimal("0.00"),
            )

            if total_spent < campaign.minimum_spent:
                return (
                    False,
                    (
                        "Você ainda não atingiu o valor mínimo "
                        "de compras para este cupom."
                    ),
                )

        return True, None

    if audience == AudienceType.INACTIVE:
        last_order = orders.first()

        if not last_order:
            return (
                False,
                (
                    "Este cupom é destinado a clientes "
                    "que já compraram nesta loja."
                ),
            )

        inactive_days = (
            timezone.now().date()
            - last_order.created_at.date()
        ).days

        required_days = (
            campaign.inactive_days
            or 0
        )

        if inactive_days < required_days:
            return (
                False,
                (
                    "Este cupom é destinado a clientes "
                    f"sem comprar há pelo menos {required_days} dias."
                ),
            )

        return True, None

    return (
        False,
        "Não foi possível validar o público deste cupom.",
    )


def validate_minimum_order(
    campaign,
    subtotal,
):
    subtotal = Decimal(subtotal)

    minimum = (
        campaign.minimum_order_value
        or Decimal("0.00")
    )

    if subtotal < minimum:
        return (
            False,
            (
                "Pedido mínimo de "
                f"R$ {minimum:.2f} para usar este cupom."
            ).replace(".", ","),
        )

    return True, None


def validate_free_delivery(
    campaign,
    delivery_fee,
):
    delivery_fee = Decimal(delivery_fee)

    if (
        campaign.discount_type == DiscountType.FREE_DELIVERY
        and delivery_fee <= Decimal("0.00")
    ):
        return (
            False,
            "Este cupom é válido apenas para pedidos com entrega.",
        )

    return True, None


def calculate_discount(
    campaign,
    subtotal,
    delivery_fee,
):
    subtotal = money(subtotal)
    delivery_fee = money(delivery_fee)

    if campaign.discount_type == DiscountType.PERCENTAGE:
        discount = (
            subtotal
            * campaign.discount_value
            / Decimal("100")
        )

        return money(
            min(
                discount,
                subtotal,
            )
        )

    if campaign.discount_type == DiscountType.FIXED_AMOUNT:
        return money(
            min(
                campaign.discount_value,
                subtotal,
            )
        )

    if campaign.discount_type == DiscountType.FREE_DELIVERY:
        return money(delivery_fee)

    return Decimal("0.00")


def validate_coupon(
    *,
    code,
    tenant,
    customer,
    subtotal,
    delivery_fee,
):
    if not customer:
        return {
            "valid": False,
            "message": "Entre na sua conta para usar cupons.",
        }

    code = (
        code
        .strip()
        .upper()
    )

    campaign = (
        CouponCampaign.objects
        .filter(
            tenant=tenant,
            code__iexact=code,
        )
        .first()
    )

    if not campaign:
        return {
            "valid": False,
            "message": "Cupom inválido.",
        }

    validations = [
        validate_campaign_period(campaign),
        validate_usage_limits(
            campaign,
            customer,
        ),
        validate_audience(
            campaign,
            customer,
        ),
        validate_minimum_order(
            campaign,
            subtotal,
        ),
        validate_free_delivery(
            campaign,
            delivery_fee,
        ),
    ]

    for valid, message in validations:
        if not valid:
            return {
                "valid": False,
                "message": message,
            }

    discount = calculate_discount(
        campaign,
        subtotal,
        delivery_fee,
    )

    final_total = money(
        Decimal(subtotal)
        + Decimal(delivery_fee)
        - discount
    )

    return {
        "valid": True,
        "campaign": campaign,
        "discount": discount,
        "final_total": money(
            max(
                final_total,
                Decimal("0.00"),
            )
        ),
        "message": "Cupom aplicado com sucesso.",
    }
