"""Shell-only bounded reconciliation for the 99Food sandbox quarantine."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_webhook_batch import reconcile_batch


class Command(BaseCommand):
    help = 'Reconcilia lote limitado de webhooks sandbox 99Food; não cria Orders/KDS nem envia comandos.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', required=True)
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        try:
            result = reconcile_batch(tenant_slug=options['tenant'], limit=options['limit'],
                                     apply=options['apply'])
        except ProviderError:
            raise CommandError('Lote não autorizado para o sandbox isolado.') from None
        for item in result['events']:
            self.stdout.write(f"evento={item['event_id']} resultado={item['result']}")
        self.stdout.write(f"selecionados={result['selected']} ok={result['ok']} "
                          f"revisao={result['failed']} aplicado={result['applied']}")
        if result['failed']:
            raise CommandError('Existem eventos que exigem revisão; nenhum foi confirmado à 99Food.')
