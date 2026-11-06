from datetime import timedelta
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import SalesSettings
from .cart_service import CartError, ensure_store


def validate_schedule(tenant, value, mode):
    if not value:
        return None
    ensure_store(tenant)
    cfg = SalesSettings.objects.filter(tenant=tenant, scheduling_enabled=True).first()
    if not cfg:
        raise CartError("Esta loja não aceita pedidos agendados.")
    if mode not in ("delivery", "pickup") or not getattr(tenant, "accepts_" + mode):
        raise CartError("Modalidade indisponível nesta loja.")
    try:
        target = parse_datetime(value) if isinstance(value, str) else value
        if target is None:
            raise ValueError
        if timezone.is_naive(target):
            target = timezone.make_aware(target)
    except (TypeError, ValueError, AttributeError):
        raise CartError("Informe uma data e horário válidos.") from None
    now = timezone.now()
    if target < now + timedelta(minutes=cfg.lead_minutes) or target > now + timedelta(
        days=cfg.horizon_days
    ):
        raise CartError(
            f"Agende com pelo menos {cfg.lead_minutes} minutos e no máximo {cfg.horizon_days} dias de antecedência."
        )
    local = timezone.localtime(target)
    for row in tenant.business_hours.filter(is_closed=False):
        start, end = row.opening_time, row.closing_time
        if not start or not end:
            continue
        if (
            start < end
            and row.weekday == local.weekday()
            and start <= local.time() < end
        ):
            return target
        if start > end and (
            (row.weekday == local.weekday() and local.time() >= start)
            or ((row.weekday + 1) % 7 == local.weekday() and local.time() < end)
        ):
            return target
    raise CartError("Escolha um horário dentro do funcionamento da loja.")
