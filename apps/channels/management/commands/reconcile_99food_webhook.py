"""Reconcile a single already-signed 99Food sandbox event from shell only."""
from django.core.management.base import BaseCommand, CommandError

from apps.channels.connectors import ProviderError
from apps.channels.food99_webhook_reconcile import reconcile


class Command(BaseCommand):
    help = 'Inspeciona ou reconcilia na quarentena um webhook 99Food assinado, sem ACK ou Orders.'

    def add_arguments(self, parser):
        parser.add_argument('--event-id', type=int, required=True)
        parser.add_argument('--apply', action='store_true', help='Consulta GET e atualiza a quarentena; sem pedido operacional.')

    def handle(self, *args, **options):
        try:
            result = reconcile(options['event_id'], apply=options['apply'])
        except ProviderError:
            # Never expose provider responses, tokens, or customer details.
            raise CommandError('Reconciliação não autorizada ou dados externos inválidos.') from None
        except Exception:
            # Intentionally avoid leaking raw exceptions to shell logs.
            raise CommandError('Reconciliação interrompida; consulte a integridade do ambiente.') from None
        for key in ('event_id', 'event_type', 'order_id', 'state', 'staged', 'acknowledged', 'operational'):
            self.stdout.write(f'{key}={result[key]}')
