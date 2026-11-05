"""Explicit sandbox local replay of signed 99Food events already linked to Orders."""
import json
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_backlog import run_backlog


class Command(BaseCommand):
    help = 'Paginação segura dos webhooks de pedidos importados; sem POST à 99Food.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', required=True)
        parser.add_argument('--limit', type=int, default=50)
        parser.add_argument('--cursor', type=int, default=0)
        parser.add_argument('--pages', type=int, default=1)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **opts):
        if not 1 <= opts['pages'] <= 20:
            raise CommandError('pages deve estar entre 1 e 20.')
        cursor = opts['cursor']
        reports = []
        try:
            for _ in range(opts['pages']):
                report = run_backlog(tenant_slug=opts['tenant'], limit=opts['limit'],
                                     cursor=cursor, apply=opts['apply'])
                reports.append(report)
                if not report['has_more']:
                    break
                cursor = report['next_cursor']
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
        summary = {'pages': len(reports), 'selected': sum(p['selected'] for p in reports),
                   'updated': sum(p['updated'] for p in reports),
                   'has_more': reports[-1]['has_more'],
                   'next_cursor': reports[-1]['next_cursor'],
                   'applied': bool(opts['apply']), 'provider_writes': 0}
        if opts['json']:
            self.stdout.write(json.dumps({'summary': summary, 'reports': reports}, ensure_ascii=False))
        else:
            self.stdout.write(str(summary))
            for report in reports:
                for result in report['results']:
                    self.stdout.write('event_id=%s result=%s' % (result['event_id'], result['result']))
