"""Run the optional local-only sandbox event projection via Django shell."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_local_sync import sync_batch


class Command(BaseCommand):
    help = 'Sincroniza eventos assinados 99Food com pedidos sandbox já importados; sem chamadas remotas.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', required=True)
        parser.add_argument('--limit', type=int, default=50)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        try:
            data = sync_batch(tenant_slug=options['tenant'], limit=options['limit'],
                              apply=options['apply'])
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(f"selected={data['selected']} updated={data['updated']} applied={data['applied']}")
        for event in data['events']:
            self.stdout.write(f"event_id={event['event_id']} result={event['result']}")
