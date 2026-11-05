"""Read-only checklist usable from the HML backend container."""
import json
from django.core.management.base import BaseCommand, CommandError
from apps.channels.food99_readiness import build_readiness
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = 'Audita o preparo 99Food em homologação, SEM chamadas remotas e SEM alterações.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-slug', required=True)
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        slug = options['tenant_slug']
        tenant = Tenant.objects.filter(slug=slug).first()
        if not tenant:
            raise CommandError('Tenant não encontrado.')
        try:
            result = build_readiness(tenant=tenant)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if options['json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return
        self.stdout.write('99Food — auditoria local somente leitura')
        for section in ('internal_checks', 'external_checks'):
            for item in result[section]:
                self.stdout.write('%s | %s | %s' % (item['state'].upper(), item['key'], item['detail']))
        self.stdout.write('Liberado para produção: NÃO. Pendências externas: %s.' % result['external_pending'])
