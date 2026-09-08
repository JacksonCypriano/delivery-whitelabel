from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.billing.fiscal_models import fiscal_today
from apps.billing.models import FiscalSettings, TaxRate
from apps.billing.provider import environment
from apps.billing.tasks import _tax_rate_admin_url
from apps.integrations.whatsapp.client import EvolutionClient, EvolutionError
from apps.integrations.whatsapp.service import normalize_br_phone


class Command(BaseCommand):
    help = (
        "Envia uma mensagem de TESTE do lembrete mensal de ISS para o WhatsApp "
        "administrativo do superusuário. Não cria pendência nem marca lembrete mensal como enviado."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            help="Enviar somente para este superusuário. Vazio: todos os superusuários ativos com WhatsApp.",
        )

    def handle(self, *args, **options):
        env = environment()
        config = FiscalSettings.objects.filter(environment=env).first()
        if not config:
            raise CommandError("Configuração fiscal do ambiente não encontrada.")

        month = fiscal_today().replace(day=1)
        current = TaxRate.objects.filter(configuration=config, month=month).first()
        previous = (
            TaxRate.objects.filter(
                configuration=config,
                month__lt=month,
                checked_at__isnull=False,
            )
            .order_by("-month", "-checked_at")
            .first()
        )
        action_url = _tax_rate_admin_url(
            {
                "configuration": config,
                "month": month,
                "current": current,
                "previous": previous,
            }
        )
        if not action_url:
            raise CommandError(
                "SUPERADMIN_PUBLIC_URL inválida. Use uma URL HTTPS pública que abra no celular."
            )

        contabilizei_url = getattr(
            settings,
            "CONTABILIZEI_TAX_RATES_URL",
            "https://app.contabilizei.com.br/painel-de-controle/#/minhas-aliquotas",
        )
        text = (
            "🧪 TESTE — VemDeDelivery · lembrete mensal do ISS\n\n"
            "Esta é uma mensagem de teste. Nenhuma alíquota foi alterada e nenhum lembrete mensal foi consumido.\n\n"
            "1) Conferir a alíquota na Contabilizei:\n"
            f"{contabilizei_url}\n\n"
            "2) Confirmar ou alterar no Superadmin do VemDeDelivery:\n"
            f"{action_url}\n\n"
            "Quando uma nova competência estiver pendente, você receberá automaticamente um aviso semelhante."
        )

        User = get_user_model()
        users = User.objects.filter(is_superuser=True, is_active=True).exclude(
            administrative_whatsapp=""
        )
        username = (options.get("username") or "").strip()
        if username:
            users = users.filter(username=username)
        users = list(users.order_by("pk"))
        if not users:
            raise CommandError(
                "Nenhum superusuário ativo com WhatsApp administrativo foi encontrado."
            )

        sent = 0
        for user in users:
            try:
                phone = normalize_br_phone(user.administrative_whatsapp)
                EvolutionClient().send_text(phone, text)
            except (ValueError, EvolutionError) as exc:
                reason = getattr(exc, "reason", "invalid_phone")
                raise CommandError(
                    f"Falha ao enviar o teste para o superusuário pk={user.pk}: {reason}."
                ) from exc
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"Mensagem de teste enviada para {sent} superusuário(s)."))
