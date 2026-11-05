"""Read-only forensic check on HML for tenant-bound 99Food rows."""
import json
from django.core.management.base import BaseCommand, CommandError
from apps.channels.food99_integrity_audit import inspect_integrity
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = 'Verifica integridade local da 99Food sem alterar pedidos nem acessar APIs externas.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-slug', required=True)
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options['tenant_slug']).first()
        if tenant is None:
            raise CommandError('Tenant não encontrado.')
        try:
            report = inspect_integrity(tenant=tenant, limit=options['limit'])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if options['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
            return
        self.stdout.write('99Food — integridade local; sem POST e sem alterações')
        for issue in report['issues']:
            self.stdout.write('%s | %s | pedido=%s comando=%s evento=%s' % (
                issue['severity'], issue['code'], issue['order_pk'],
                issue['command_pk'], issue['event_pk']))
        self.stdout.write('Achados: %d; possível truncamento: %s' % (
            len(report['issues']), report['truncated']))
