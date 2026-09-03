from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from apps.billing.models import BillingSettings, Subscription


class Command(BaseCommand):
    help = (
        "Verifica configuração de assinaturas sem emitir cobrança nem acessar o Asaas."
    )

    def handle(self, *args, **options):
        policy = BillingSettings.current()
        self.stdout.write(
            f"Ambiente: {settings.ASAAS_ENVIRONMENT}; módulo habilitado: {settings.BILLING_ENABLED}"
        )
        self.stdout.write(
            f"Tolerância global: {policy.grace_days} dias; execução diária: 06:00 America/Sao_Paulo"
        )
        self.stdout.write(
            f"Lojas com controle: {Subscription.objects.filter(managed=True).count()}; sem controle: {Subscription.objects.filter(managed=False).count()}"
        )
        if not settings.BILLING_ENABLED:
            self.stdout.write(
                "Cobranças e suspensão automática desabilitadas até a configuração."
            )
            return
        errors = []
        if settings.ASAAS_ENVIRONMENT not in ("sandbox", "production"):
            errors.append("ASAAS_ENVIRONMENT deve ser sandbox ou production.")
        if settings.ASAAS_ENVIRONMENT == "sandbox" and not getattr(
            settings, "BILLING_ALLOW_SANDBOX", True
        ):
            errors.append("Não use sandbox na aplicação de produção.")
        if not settings.ASAAS_API_KEY:
            errors.append("Configure ASAAS_API_KEY no ambiente correto.")
        if len(settings.ASAAS_WEBHOOK_TOKEN) < 32:
            errors.append(
                "Configure ASAAS_WEBHOOK_TOKEN com pelo menos 32 caracteres aleatórios."
            )
        if settings.CELERY_TIMEZONE != "America/Sao_Paulo":
            errors.append("Fuso Celery incorreto.")
        if errors:
            raise CommandError("\n".join(errors))
        self.stdout.write(
            self.style.SUCCESS(
                "Configuração local aprovada. Valide chave, webhook e pagamento no sandbox antes de produção."
            )
        )
