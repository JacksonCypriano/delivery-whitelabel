"""Explicit async GA4 Measurement Protocol upload, invoked by cron/beat only.

Never send to Google in the Asaas webhook or a database transaction. Each event
has a local delivery ledger; ambiguous failures are held for manual inspection.
"""
from datetime import timedelta
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.marketplace.acquisition import reconcile_paid
from apps.marketplace.models import MarketingMilestone, MarketingPaidConversion


class Command(BaseCommand):
    help = "Reconcilia aquisição e envia eventos de cadastro/cobrança/pagamento ao GA4 consentido."

    def add_arguments(self, parser):
        parser.add_argument("--reconcile-only", action="store_true")
        parser.add_argument("--retry-errors", action="store_true", help="Pode reenviar eventos após timeout; valide manualmente antes.")
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **opts):
        reconcile_paid(limit=2000)
        if opts["reconcile_only"]:
            return self.stdout.write("Reconciliação local concluída (sem requisição ao Google).")
        mid = getattr(settings, "MARKETING_GA4_MEASUREMENT_ID", "").strip()
        secret = getattr(settings, "MARKETING_GA4_API_SECRET", "").strip()
        if not mid or not secret:
            raise CommandError("Configure MARKETING_GA4_MEASUREMENT_ID e MARKETING_GA4_API_SECRET.")

        milestone_qs = MarketingMilestone.objects.select_related("lead", "invoice").filter(
            ga4_sent_at__isnull=True, lead__analytics_consent=True,
        ).exclude(lead__ga_client_id="")
        payment_qs = MarketingPaidConversion.objects.select_related("lead", "invoice").filter(
            ga4_sent_at__isnull=True, lead__analytics_consent=True, retracted_at__isnull=True,
        ).exclude(lead__ga_client_id="")
        if not opts["retry_errors"]:
            milestone_qs = milestone_qs.filter(ga4_last_error="")
            payment_qs = payment_qs.filter(ga4_last_error="")
        queue = (
            [(obj.occurred_at, obj, obj.name) for obj in milestone_qs] +
            [(obj.paid_at, obj, "subscription_paid") for obj in payment_qs]
        )
        queue.sort(key=lambda item: item[0])
        sent, ignored = 0, 0
        for occurred_at, obj, name in queue[:max(1, min(opts["limit"], 1000))]:
            if not occurred_at or timezone.now() - occurred_at > timedelta(hours=70):
                ignored += 1
                continue  # Old event: not backdatable by GA4 MP.
            params = {"engagement_time_msec": 1}
            if name == "subscription_paid":
                params.update({
                    "currency": "BRL", "value": float(obj.amount),
                    "transaction_id": "vdd-first-" + str(obj.invoice_id),
                })
            else:
                params["milestone_id"] = f"vdd-{obj.lead.reference}-{name}"
            payload = {
                "client_id": obj.lead.ga_client_id,
                "timestamp_micros": int(occurred_at.timestamp() * 1_000_000),
                "events": [{"name": name, "params": params}],
            }
            try:
                res = requests.post(
                    "https://www.google-analytics.com/mp/collect",
                    params={"measurement_id": mid, "api_secret": secret},
                    json=payload, timeout=8,
                )
                res.raise_for_status()
            except requests.RequestException as exc:
                obj.ga4_last_error = type(exc).__name__[:250]
                obj.save(update_fields=["ga4_last_error"])
                ignored += 1
                continue
            obj.ga4_sent_at = timezone.now()
            obj.ga4_last_error = ""
            obj.save(update_fields=["ga4_sent_at", "ga4_last_error"])
            sent += 1
        self.stdout.write(f"GA4: aceitos HTTP={sent}, ignorados/retidos={ignored}. Confirme processamento nos relatórios.")
