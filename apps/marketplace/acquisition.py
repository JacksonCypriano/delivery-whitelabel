"""Marketing attribution for the manual WhatsApp -> Superadmin -> Asaas funnel.

No personally identifying WhatsApp text/phone/email is sent to Analytics.
Attribution is optional; the customer-facing checkout never depends on it.
"""
import logging
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

log = logging.getLogger(__name__)
REFERENCE_RE = re.compile(r"^VDD-[A-F0-9]{10}$")
CLICK_SALT = "marketing-whatsapp-click-v1"
CLICK_TTL = 30 * 60
AD_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "gbraid", "wbraid")


def new_contact(request):
    """Return a signed, per-render ref; do not write to DB on mere page views."""
    reference = "VDD-" + secrets.token_hex(5).upper()
    token = signing.dumps({"reference": reference, "path": request.path[:220]}, salt=CLICK_SALT)
    number = getattr(settings, "MARKETING_WHATSAPP", "5511964059470").strip()
    message = (
        "Olá! Conheci o VemDeDelivery pelo site e quero contratar para minha loja. "
        f"Como começamos? Referência: {reference}"
    )
    return {"reference": reference, "token": token, "url": f"https://wa.me/{number}?" + urlencode({"text": message})}


def record_click(*, token, cta, consent, attribution):
    """Persist only CTA clicks. Signed token prevents arbitrary anonymous insertions."""
    from .models import MarketingLead

    payload = signing.loads(token, salt=CLICK_SALT, max_age=CLICK_TTL)
    reference = payload.get("reference", "")
    if not REFERENCE_RE.fullmatch(reference):
        raise signing.BadSignature("Referência inválida")
    path = str(payload.get("path", ""))
    if not path.startswith("/") or len(path) > 220 or path.startswith("//"):
        raise signing.BadSignature("Caminho inválido")
    is_consented = consent is True
    allowed = {
        key: str(attribution.get(key, ""))[:180] if is_consented else ""
        for key in AD_FIELDS
    }
    client_id = str(attribution.get("ga_client_id", ""))[:80] if is_consented else ""
    if not re.fullmatch(r"[0-9]{1,20}\.[0-9]{1,20}", client_id):
        client_id = ""
    with transaction.atomic():
        lead, created = MarketingLead.objects.get_or_create(
            reference=reference,
            defaults={
                "landing_path": path,
                "cta": str(cta)[:64],
                "analytics_consent": is_consented,
                "ga_client_id": client_id,
                **allowed,
            },
        )
        # Never rewrite a lead's attribution from duplicate clicks.
        return lead, created


def link_lead(tenant, reference):
    """Called inside the Superadmin tenant transaction. Never guesses the source."""
    from .models import MarketingLead
    from apps.billing.models import Invoice

    reference = (reference or "").strip().upper()
    if not reference:
        return None
    if not REFERENCE_RE.fullmatch(reference):
        raise ValueError("Referência comercial inválida")
    with transaction.atomic():
        lead, _ = MarketingLead.objects.select_for_update().get_or_create(
            reference=reference, defaults={"landing_path": "", "cta": "manual", "source_note": "manual_unverified"}
        )
        if lead.tenant_id and lead.tenant_id != tenant.pk:
            raise ValueError("Referência já vinculada a outra loja")
        lead.tenant = tenant
        if not lead.linked_at:
            lead.linked_at = timezone.now()
        lead.save(update_fields=["tenant", "linked_at"])
        record_signup(lead, tenant.created_at or timezone.now())
        # Recovery: an admin can associate a lead after an invoice was issued.
        first_issued = Invoice.objects.filter(
            tenant=tenant, months__gt=0, additional_service__isnull=True,
            environment="production", status__in=("PENDING", "OVERDUE", "PAID", "REVIEW")
        ).order_by("created_at").first()
        if first_issued:
            record_invoice_created(first_issued)
        # Recovery: an admin can associate a lead after an invoice was paid.
        for bill in Invoice.objects.filter(tenant=tenant, status="PAID", months__gt=0, additional_service__isnull=True, environment="production").order_by("paid_at", "created_at")[:1]:
            record_first_payment(bill)
        return lead


def record_first_payment(invoice):
    """Local idempotent ledger: only FIRST genuine paid subscription per lead.

    Invoked after a verified Asaas payment has been committed (also by backfill).
    Never invokes a network call or changes billing status.
    """
    from .models import MarketingLead, MarketingPaidConversion
    if (invoice.status != "PAID" or invoice.environment != "production"
            or invoice.months <= 0 or invoice.additional_service_id is not None):
        return None
    with transaction.atomic():
        lead = MarketingLead.objects.select_for_update().filter(tenant_id=invoice.tenant_id).first()
        if not lead:
            return None
        # Do not mistake a renewal for a first acquisition. Reversed payments
        # (REVIEW) are excluded; the next genuine paid invoice may replace one
        # that was previously retracted in our *local* ledger.
        first = invoice.__class__.objects.filter(
            tenant_id=invoice.tenant_id, status="PAID", environment="production",
            months__gt=0, additional_service__isnull=True,
        ).order_by("paid_at", "created_at", "pk").first()
        if not first or first.pk != invoice.pk:
            return None
        existing = MarketingPaidConversion.objects.filter(lead=lead).first()
        if existing:
            if existing.retracted_at and existing.invoice_id != invoice.pk:
                existing.invoice = invoice
                existing.amount = invoice.amount
                existing.paid_at = invoice.paid_at or timezone.now()
                existing.retracted_at = None
                existing.ga4_sent_at = None
                existing.ga4_last_error = ""
                existing.save(update_fields=[
                    "invoice", "amount", "paid_at", "retracted_at", "ga4_sent_at", "ga4_last_error"
                ])
            return existing
        conv, _ = MarketingPaidConversion.objects.get_or_create(
            lead=lead,
            defaults={"invoice": invoice, "amount": invoice.amount, "paid_at": invoice.paid_at or timezone.now()},
        )
        return conv


def reconcile_paid(*, limit=250):
    """Reconcile payments when a signal/callback was lost; idempotent."""
    from apps.billing.models import Invoice
    qs = Invoice.objects.filter(
        tenant__marketing_lead__isnull=False, status="PAID", environment="production",
        months__gt=0, additional_service__isnull=True
    ).order_by("paid_at", "created_at")[:limit]
    for invoice in qs:
        record_first_payment(invoice)


def record_signup(lead, occurred_at):
    from .models import MarketingMilestone
    return MarketingMilestone.objects.get_or_create(
        lead=lead, name="signup_completed", defaults={"occurred_at": occurred_at}
    )[0]


def record_invoice_created(invoice):
    from .models import MarketingLead, MarketingMilestone
    if (invoice.environment != "production" or invoice.months <= 0
            or invoice.additional_service_id is not None
            or invoice.status not in ("PENDING", "OVERDUE", "PAID", "REVIEW")):
        return None
    lead = MarketingLead.objects.filter(tenant_id=invoice.tenant_id).first()
    if not lead:
        return None
    return MarketingMilestone.objects.get_or_create(
        lead=lead, name="subscription_created",
        defaults={"invoice": invoice, "occurred_at": invoice.created_at or timezone.now()},
    )[0]


def reflect_payment_review(invoice):
    """Stop new exports of reversed/contested acquisitions; flag exports already sent."""
    from .models import MarketingPaidConversion
    conversion = MarketingPaidConversion.objects.filter(invoice=invoice).first()
    if not conversion:
        return
    if invoice.status == "REVIEW" and conversion.retracted_at is None:
        conversion.retracted_at = timezone.now()
        conversion.save(update_fields=["retracted_at"])
    elif invoice.status == "PAID" and conversion.retracted_at is not None:
        conversion.retracted_at = None
        conversion.save(update_fields=["retracted_at"])


def mark_qualified(lead):
    """Only call after a human verifies that WhatsApp conversation happened."""
    from .models import MarketingMilestone
    if not lead.qualified_at:
        lead.qualified_at = timezone.now()
        lead.save(update_fields=["qualified_at"])
    return MarketingMilestone.objects.get_or_create(
        lead=lead, name="lead_qualified", defaults={"occurred_at": lead.qualified_at}
    )[0]
