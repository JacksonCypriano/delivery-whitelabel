"""Recover signed sandbox events after broker outages (no external writes)."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_async_reconcile import select_event_ids
from apps.channels.tasks import consume_99food_sandbox_event


class Command(BaseCommand):
    help = 'Consulta a fila durável de webhooks 99Food de teste; --enqueue envia tarefas ao Celery.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', required=True)
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--enqueue', action='store_true')

    def handle(self, *args, **options):
        try:
            ids = select_event_ids(tenant_slug=options['tenant'], limit=options['limit'])
            if not options['enqueue']:
                self.stdout.write('Elegíveis: %s. Simulação; nenhum evento enviado.' % len(ids))
                return
            count = 0
            for event_id in ids:
                consume_99food_sandbox_event.delay(event_id)
                count += 1
            self.stdout.write(self.style.SUCCESS('Eventos enfileirados: %s' % count))
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
        except Exception:
            raise CommandError('Não foi possível enfileirar os eventos; confira o worker e tente novamente.') from None
