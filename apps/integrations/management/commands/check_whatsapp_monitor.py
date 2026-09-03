from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.integrations.whatsapp.monitor import enabled, identity
from apps.integrations.models import WhatsAppIntegrationState


class Command(BaseCommand):
    help = "Verifica configuração/atividade local do monitor WhatsApp, sem chamar a Evolution."

    def add_arguments(self, parser):
        parser.add_argument("--require-fresh", action="store_true")

    def handle(self, *args, **options):
        if not enabled():
            self.stdout.write("Monitoramento WhatsApp desabilitado neste ambiente.")
            return
        if not all(
            (
                settings.EVOLUTION_API_URL,
                settings.EVOLUTION_API_KEY,
                settings.EVOLUTION_INSTANCE,
            )
        ):
            raise CommandError("Configuração da Evolution incompleta.")
        if settings.EVOLUTION_MONITOR_ENVIRONMENT not in {
            "homolog",
            "prod",
            "local",
            "demo",
        }:
            raise CommandError("Ambiente do monitor inválido.")
        if not settings.EVOLUTION_ALERT_EMAILS:
            raise CommandError(
                "Configure EVOLUTION_ALERT_EMAILS para a administração da plataforma."
            )
        try:
            for recipient in settings.EVOLUTION_ALERT_EMAILS:
                validate_email(recipient)
        except ValidationError:
            raise CommandError("E-mail de alerta inválido.") from None
        if len(settings.EVOLUTION_WEBHOOK_TOKEN) < 32:
            self.stdout.write(
                "AVISO: webhook desabilitado; configure token exclusivo com pelo menos 32 caracteres. Consulta periódica continua disponível."
            )
        if options["require_fresh"]:
            row = WhatsAppIntegrationState.objects.filter(identity=identity()).first()
            if (
                not row
                or not row.checked_at
                or timezone.now() - row.checked_at > timedelta(minutes=3)
            ):
                raise CommandError(
                    "Verificação WhatsApp atrasada. Confira Celery/Beat."
                )
            if row.status != "open":
                raise CommandError("WhatsApp não conectado. Consulte o superadmin.")
        self.stdout.write(
            "Configuração local aprovada. Confirme endpoints, webhook, alertas e reconexão na instância de teste."
        )
