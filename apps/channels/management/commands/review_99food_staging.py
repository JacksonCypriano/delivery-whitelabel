"""Read-only status and revision history of quarantined 99Food orders."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.models import Food99StagedOrder


class Command(BaseCommand):
    help = 'Lista a quarentena 99Food sem revelar snapshots ou dados pessoais.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-slug', required=True)
        parser.add_argument('--order-id')
        parser.add_argument('--limit', type=int, default=20)

    def handle(self, *args, **opts):
        if not 1 <= opts['limit'] <= 100:
            raise CommandError('--limit deve estar entre 1 e 100.')
        q = Food99StagedOrder.objects.filter(
            connection__provider='99food', connection__mode='test',
            connection__tenant__slug=opts['tenant_slug'],
        )
        if opts['order_id']:
            q = q.filter(external_id=opts['order_id'])
        self.stdout.write('pedido,status,versoes,alteracoes,estado,ultima_atualizacao')
        for row in q.order_by('-updated_at')[:opts['limit']]:
            revisions = row.revisions.count()
            self.stdout.write(f'{row.external_id},{row.last_seen_status},{revisions},'
                              f'{row.change_count},{row.state},{row.updated_at.isoformat()}')
        self.stdout.write('Consulta somente leitura; sem Order/KDS/ações remotas.')
