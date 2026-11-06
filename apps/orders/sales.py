"""Opt-in automation planner and outbox. No network writes in HTTP requests."""

from datetime import timedelta
import re
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.customers.models import Customer
from apps.marketplace.services import build_tenant_url
from .models import Cart, Order, SalesSettings, MarketingConsent, SalesMessage
from .operations import operational_order_q


def eligible_customer(tenant, customer):
    return bool(
        customer
        and customer.phone_verified
        and MarketingConsent.objects.filter(
            tenant=tenant, customer=customer, allowed=True
        ).exists()
    )


def queue(cfg, customer, kind, key, **kwargs):
    if not eligible_customer(cfg.tenant, customer):
        return
    return SalesMessage.objects.get_or_create(
        tenant=cfg.tenant,
        key=key,
        defaults={"customer": customer, "kind": kind, **kwargs},
    )[0]


@shared_task
def plan_sales_messages():
    now = timezone.now()
    for cfg in SalesSettings.objects.select_related("tenant").filter(
        tenant__is_active=True
    ):
        if cfg.recovery_enabled:
            for cart in Cart.objects.filter(
                tenant=cfg.tenant,
                user__isnull=False,
                updated_at__lte=now - timedelta(minutes=cfg.recovery_minutes),
                updated_at__gte=now - timedelta(days=7),
            ).select_related("user"):
                if (
                    not cart.items.exists()
                    or Order.objects.filter(tenant=cfg.tenant, source_cart_id=cart.pk)
                    .filter(operational_order_q())
                    .filter(created_at__gte=cart.updated_at)
                    .exists()
                ):
                    continue
                customer = Customer.objects.filter(user=cart.user).first()
                if customer:
                    queue(
                        cfg,
                        customer,
                        "recovery",
                        f"cart:{cart.pk}:{cart.checkout_token}",
                        cart=cart,
                    )
        if cfg.feedback_enabled:
            for order in Order.objects.filter(
                tenant=cfg.tenant,
                status="delivered",
                customer__isnull=False,
                status_updated_at__lte=now - timedelta(minutes=cfg.feedback_minutes),
                status_updated_at__gte=now - timedelta(days=7),
            ).select_related("customer"):
                queue(
                    cfg, order.customer, "feedback", f"feedback:{order.pk}", order=order
                )
        if cfg.reactivation_enabled:
            for consent in MarketingConsent.objects.filter(
                tenant=cfg.tenant, allowed=True
            ).select_related("customer"):
                last = (
                    Order.objects.filter(
                        tenant=cfg.tenant, customer=consent.customer, status="delivered"
                    )
                    .order_by("-created_at")
                    .first()
                )
                if last and last.created_at < now - timedelta(days=cfg.inactive_days):
                    queue(
                        cfg,
                        consent.customer,
                        "reactivation",
                        f"reactivate:{last.pk}",
                        order=last,
                    )
    # Conversion is observational; never changes the order or payment.
    for notice in SalesMessage.objects.filter(
        sent_at__isnull=False, converted_at__isnull=True
    ).exclude(kind="feedback"):
        if (
            Order.objects.filter(
                tenant=notice.tenant,
                customer=notice.customer,
                created_at__gt=notice.sent_at,
            )
            .filter(operational_order_q())
            .exists()
        ):
            SalesMessage.objects.filter(pk=notice.pk).update(converted_at=now)
    for pk in (
        SalesMessage.objects.filter(
            attempted_at__isnull=True, sent_at__isnull=True, skipped_at__isnull=True
        )
        .order_by("created_at")
        .values_list("pk", flat=True)[:100]
    ):
        deliver_sales_message(pk)


@shared_task(soft_time_limit=45, time_limit=60)
def deliver_sales_message(pk):
    if not getattr(settings, "WHATSAPP_AGENT_ENABLED", False):
        return "disabled"
    from apps.integrations.models import TenantWhatsAppAgent, TenantWhatsAppConversation
    from apps.integrations.whatsapp_agent.client import TenantEvolutionClient
    from apps.integrations.whatsapp.client import EvolutionError

    with transaction.atomic():
        notice = (
            SalesMessage.objects.select_for_update(of=("self",))
            .select_related("tenant", "customer", "cart", "order", "campaign")
            .filter(pk=pk)
            .first()
        )
        if not notice or notice.attempted_at or notice.sent_at or notice.skipped_at:
            return "duplicate"
        now = timezone.now()
        cfg = SalesSettings.objects.filter(tenant=notice.tenant).first()
        valid = bool(
            cfg
            and notice.tenant.is_active
            and eligible_customer(notice.tenant, notice.customer)
            and getattr(cfg, notice.kind + "_enabled", False)
        )
        if notice.kind == "campaign":
            valid = bool(
                notice.campaign
                and notice.campaign.tenant_id == notice.tenant_id
                and notice.campaign.active
                and notice.tenant.is_active
                and eligible_customer(notice.tenant, notice.customer)
            )
        if notice.kind == "campaign" and valid:
            from .crm import customers

            valid = any(
                c["id"] == notice.customer_id
                and notice.campaign.segment in c["segments"]
                for c in customers(notice.tenant)
            )
        if notice.created_at < now - timedelta(days=7):
            valid = False
        if notice.kind == "recovery":
            valid = valid and bool(
                notice.cart
                and notice.cart.items.exists()
                and notice.key == f"cart:{notice.cart.pk}:{notice.cart.checkout_token}"
            )
            if (
                notice.cart
                and Order.objects.filter(
                    tenant=notice.tenant,
                    source_cart_id=notice.cart_id,
                    created_at__gte=notice.cart.updated_at,
                )
                .filter(operational_order_q())
                .exists()
            ):
                valid = False
        elif notice.kind == "feedback":
            valid = valid and bool(notice.order and notice.order.status == "delivered")
        elif notice.kind == "reactivation":
            valid = (
                valid
                and not Order.objects.filter(
                    tenant=notice.tenant,
                    customer=notice.customer,
                    created_at__gte=now
                    - timedelta(days=cfg.inactive_days if cfg else 30),
                )
                .filter(operational_order_q())
                .exists()
            )
        if not valid:
            notice.skipped_at = now
            notice.error = "Condições ou autorização alteradas."
            notice.save()
            return "skipped"
        # Lock the consent as the per-recipient serialization point.
        consent = MarketingConsent.objects.select_for_update(of=("self",)).get(
            tenant=notice.tenant, customer=notice.customer
        )
        if not consent.allowed:
            return "revoked"
        if (
            SalesMessage.objects.filter(
                tenant=notice.tenant,
                customer=notice.customer,
                attempted_at__gte=now - timedelta(days=7),
            )
            .exclude(pk=pk)
            .exists()
        ):
            return "cooldown"
        if not 9 <= timezone.localtime(now).hour < 21:
            return "quiet-hours"
        phone = re.sub(r"\D", "", notice.customer.phone)
        if len(phone) in (10, 11):
            phone = "55" + phone
        if TenantWhatsAppConversation.objects.filter(
            tenant=notice.tenant, phone_number=phone, ai_paused_until__gt=now
        ).exists():
            return "paused"
        agent = TenantWhatsAppAgent.objects.filter(
            tenant=notice.tenant,
            instance_created=True,
            status=TenantWhatsAppAgent.Status.OPEN,
        ).first()
        if not agent:
            return "offline"
        base = build_tenant_url(notice.tenant)
        text = {
            "recovery": f"Seu carrinho na {notice.tenant.name} continua disponível. Confira os valores e finalize: {base}checkout/cart/",
            "feedback": f"Como foi seu pedido na {notice.tenant.name}? Avalie de 1 a 5: {base}avaliacao/{notice.token}/",
            "reactivation": f"Olá! Veja as novidades da {notice.tenant.name}: {base}",
        }.get(notice.kind)
        if notice.kind == "campaign" and notice.campaign:
            text = notice.campaign.text
        if not text:
            return "unsupported"
        notice.text = (
            text
            + f"\nPara deixar de receber estas mensagens: {base}avaliacao/{notice.token}/"
        )
        notice.recipient = phone
        notice.attempted_at = now
        notice.save()
    try:
        from apps.integrations.whatsapp_agent.provider import (
            mark_outbound_pending,
            mark_outbound_message,
        )

        mark_outbound_pending(agent.instance_name, phone, notice.text)
        mid = TenantEvolutionClient().send_text(agent.instance_name, phone, notice.text)
        mark_outbound_message(agent.instance_name, mid)
    except EvolutionError:
        # A timeout may mean the provider accepted it: no automatic replay.
        SalesMessage.objects.filter(pk=pk).update(
            error="Envio não confirmado; sem repetição automática."
        )
        return "uncertain"
    SalesMessage.objects.filter(pk=pk).update(sent_at=timezone.now())
    return "sent"
