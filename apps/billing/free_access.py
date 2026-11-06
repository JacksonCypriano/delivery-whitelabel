"""Audited day grants extend the existing exclusive access deadline, not invoices."""

import uuid
from datetime import date, timedelta
from django.db import transaction
from django.utils import timezone
from .models import Subscription, FreeAccessGrant
from .provider import BillingError
from .services import get_subscription, set_store, audit


def access_state(sub, tenant):
    return {
        "active": tenant.is_active,
        "billing_suspended": sub.billing_suspended,
        "manually_blocked": sub.manually_blocked,
        "payment_review": sub.payment_review,
    }


def period(sub, days):
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise BillingError("Informe uma quantidade inteira positiva de dias.")
    today = timezone.localdate()
    start = max(today, sub.valid_until) if sub.valid_until else today
    if days > (date.max - start).days:
        raise BillingError("O período excede o limite técnico das datas (31/12/9999).")
    return start, start + timedelta(days=days)


def validate(actor, days, reason, token):
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise BillingError("Informe uma quantidade inteira positiva de dias.")
    if not actor.is_active or not actor.is_superuser:
        raise BillingError("Sem permissão para conceder gratuidade.")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500:
        raise BillingError("Informe uma justificativa de até 500 caracteres.")
    try:
        token = uuid.UUID(str(token))
    except (ValueError, TypeError, AttributeError):
        raise BillingError("Identificador da operação inválido.")
    return reason.strip(), token


def existing_grant(token, sub, days, reason, actor):
    grant = FreeAccessGrant.objects.filter(operation_id=token).first()
    if grant and (
        grant.subscription_id != sub.pk
        or grant.days != days
        or grant.reason != reason
        or grant.actor_id != actor.pk
    ):
        raise BillingError("Identificador já utilizado por outra concessão.")
    return grant


@transaction.atomic
def grant_free_days(
    tenant, days, reason, actor, token, expected_until=None, check_previous=False
):
    reason, token = validate(actor, days, reason, token)
    get_subscription(tenant)
    sub = Subscription.objects.select_for_update().get(tenant=tenant)
    prior = existing_grant(token, sub, days, reason, actor)
    if prior:
        return prior
    start, end = period(sub, days)
    if check_previous and sub.valid_until != expected_until:
        raise BillingError("A validade mudou. Confira uma nova prévia.")
    tenant = type(tenant).objects.select_for_update().get(pk=tenant.pk)
    before = access_state(sub, tenant)
    # An unexplained inactive store is not implicitly authorized for reactivation.
    if not tenant.is_active and not sub.billing_suspended:
        sub.manually_blocked = True
    previous = sub.valid_until
    sub.valid_until = end
    # Paid months extend from the resulting (exclusive) access deadline.
    # Keeping the previous anniversary would absorb gifted days in the next
    # renewal (01/12 + 7 free days + 1 paid month must end on 08/01).
    # This resets the anniversary only for an actual day grant; regular paid
    # renewals still retain their original anchor across short months.
    sub.anchor_day = end.day
    sub.managed = True
    sub.billing_suspended = False
    sub.save(
        update_fields=[
            "valid_until",
            "anchor_day",
            "managed",
            "billing_suspended",
            "manually_blocked",
        ]
    )
    set_store(sub)
    tenant.refresh_from_db(fields=["is_active"])
    grant = FreeAccessGrant.objects.create(
        operation_id=token,
        subscription=sub,
        actor=actor,
        days=days,
        reason=reason,
        previous_until=previous,
        starts_on=start,
        ends_on=end,
        access_before=before,
        access_after=access_state(sub, tenant),
    )
    audit(
        sub,
        "Dias gratuitos concedidos",
        f"{days} dias; [{start}, {end}); operação {token}; {reason}",
        actor,
    )
    return grant
