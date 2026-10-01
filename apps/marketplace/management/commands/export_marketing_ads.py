"""Export qualified, consented first-paid leads for MANUAL Ads offline import.

Creating an Ads conversion action and applying window/consent policy are separate
steps. This command DOES NOT upload or attribute non-Ads leads to Ads.
"""
import csv
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from apps.marketplace.models import MarketingPaidConversion


class Command(BaseCommand):
    help = "CSV de conversões offline para importação MANUAL no Google Ads (só com gclid e consentimento)."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="VemDeDelivery - Primeiro pagamento")

    def handle(self, *args, **options):
        writer = csv.writer(self.stdout)
        writer.writerow(["Google Click ID", "Conversion Name", "Conversion Time", "Conversion Value", "Conversion Currency", "Order ID"])
        for obj in MarketingPaidConversion.objects.select_related("lead").filter(
            lead__analytics_consent=True, retracted_at__isnull=True
        ).exclude(lead__gclid="").order_by("paid_at"):
            writer.writerow([
                obj.lead.gclid, options["name"],
                obj.paid_at.strftime("%Y-%m-%d %H:%M:%S%z"),
                str(obj.amount), "BRL", "vdd-first-" + str(obj.invoice_id),
            ])
