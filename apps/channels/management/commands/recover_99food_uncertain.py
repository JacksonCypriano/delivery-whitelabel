"""Manual dry-run default for safe recovery of abandoned one-shot commands."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_recovery import recover_stale_sending

class Command(BaseCommand):
    help = 'Analisa comandos sending antigos 99Food. --apply marca incerto SEM reenviar POST.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-slug', required=True)
        parser.add_argument('--older-than-seconds', type=int, default=120)
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        try:
            result = recover_stale_sending(tenant_slug=options['tenant_slug'],
                apply=options['apply'], older_than_seconds=options['older_than_seconds'],
                limit=options['limit'])
        except ProviderError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write('mode=%s; candidates=%s; updated=%s; remote_posts=0' % (
            result['mode'], len(result['candidate_ids']), result['updated']))
        self.stdout.write('IDs internos de comandos: %s' % result['candidate_ids'])
