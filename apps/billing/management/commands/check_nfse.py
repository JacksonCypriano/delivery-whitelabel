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
        self.stdout.write(monthly_warning(config))
        if not config.taxrate_set.filter(
            month=fiscal_today().replace(day=1), checked_at__isnull=False
        ).exists():
            raise CommandError("Falta conferir a alíquota da competência atual.")
        pending = (
            FiscalInvoice.objects.filter(invoice__environment=environment())
            .exclude(status="AUTHORIZED")
            .count()
        )
        self.stdout.write(
            f"Notas não autorizadas: {pending}. Confira também notas marcadas para revisão fiscal."
        )
        self.stdout.write(
            "Configuração local aprovada. Valide cadastro fiscal, webhook e emissão no sandbox antes de habilitar em produção."
        )
