from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.accounts.models import PendingRegistration, RegistrationRateLimit, PendingContactChange


class Command(BaseCommand):
    help = 'Remove cadastros pendentes expirados/concluídos e limites antigos de OTP.'

    def handle(self, *args, **options):
        expired, _ = PendingRegistration.objects.filter(expires_at__lte=timezone.now()).delete()
        completed, _ = PendingRegistration.objects.filter(completed_at__isnull=False).delete()
        RegistrationRateLimit.objects.filter(updated_at__lt=timezone.now() - timedelta(hours=24)).delete()
        contacts, _ = PendingContactChange.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f'{expired + completed} cadastros e {contacts} solicitações de contato removidos.')
