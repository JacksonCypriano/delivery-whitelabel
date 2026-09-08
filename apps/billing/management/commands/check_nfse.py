from django.core.management.base import BaseCommand, CommandError
from apps.billing.models import FiscalSettings, FiscalInvoice
from apps.billing.provider import environment, configured
from apps.billing.fiscal import monthly_warning
from apps.billing.fiscal_models import fiscal_today


class Command(BaseCommand):
    help = "Confere a configuração local de NFS-e; não emite notas nem consulta credenciais externas."

    def handle(self, *args, **options):
        config = FiscalSettings.objects.filter(environment=environment()).first()
        if not config or not config.enabled:
            self.stdout.write(
                "Emissão automática de NFS-e desabilitada neste ambiente."
            )
            return
        if not configured():
            raise CommandError(
                "Configure primeiro o módulo de cobranças e a conta Asaas."
            )
        config.full_clean()
        missing = config.fiscal_account_missing_fields()
        if missing:
            raise CommandError(
                "Dados fiscais locais incompletos: " + ", ".join(missing)
            )
        self.stdout.write(monthly_warning(config))
        if not config.taxrate_set.filter(
            month=fiscal_today().replace(day=1), checked_at__isnull=False
        ).exists():
            raise CommandError("Falta conferir a alíquota da competência atual.")
        notes = FiscalInvoice.objects.filter(invoice__environment=environment())
        pending = notes.exclude(status__in=("AUTHORIZED", "CANCELED")).count()
        review = (
            notes.filter(review_required=True)
            .exclude(status="CANCELED")
            .count()
        )
        canceled = notes.filter(status="CANCELED").count()
        self.stdout.write(
            f"Notas pendentes de conclusão: {pending}; "
            f"em revisão fiscal: {review}; canceladas: {canceled}."
        )
        self.stdout.write(
            "Configuração local aprovada. Valide cadastro fiscal, webhook e emissão no sandbox antes de habilitar em produção."
        )
