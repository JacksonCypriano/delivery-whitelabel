"""Minimization: purge unlinked operational click references older than 90 days."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.marketplace.models import MarketingLead


class Command(BaseCommand):
    help = "Exclui leads de cliques sem loja depois de 90 dias (não exclui pagamentos)."

    def handle(self, *args, **options):
        count, _ = MarketingLead.objects.filter(
            tenant__isnull=True,
            linked_at__isnull=True,
            first_payment__isnull=True,
            milestones__isnull=True,
            created_at__lt=timezone.now() - timedelta(days=90),
        ).delete()
        self.stdout.write(f"Registros antigos removidos: {count}.")
