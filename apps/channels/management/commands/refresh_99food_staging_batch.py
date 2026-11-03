"""Refresh existing sandbox quarantine records, bounded and without PII in logs."""
from django.core.management.base import BaseCommand, CommandError
from apps.tenants.models import Tenant
from apps.channels.models import Food99StagedOrder
from apps.channels.connectors import ProviderError
from apps.channels.food99_review_workflow import refresh_staged_order


class Command(BaseCommand):
    help = 'Atualiza até 20 pedidos existentes da quarentena 99Food; não toca no KDS.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-slug', required=True)
        parser.add_argument('--limit', type=int, default=10)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        limit = options['limit']
        if limit < 1 or limit > 20:
            raise CommandError('--limit deve estar entre 1 e 20.')
        tenant = Tenant.objects.filter(slug=options['tenant_slug']).first()
        if tenant is None:
            raise CommandError('Loja não encontrada.')
        orders = list(Food99StagedOrder.objects.filter(
            connection__tenant=tenant, connection__provider='99food',
            connection__mode='test', connection__enabled=False,
        ).order_by('pk')[:limit])
        if not options['apply']:
            self.stdout.write(f'DRY_RUN: {len(orders)} pedido(s) elegíveis; use --apply para consultar a 99Food.')
            return
        tally = {'UNCHANGED': 0, 'CHANGED_REVIEW_REQUIRED': 0,
                 'STAGED_REVIEW_REQUIRED': 0, 'ERROR': 0}
        for order in orders:
            try:
                _, result = refresh_staged_order(tenant=tenant, pk=order.pk)
                tally[result] = tally.get(result, 0) + 1
                self.stdout.write(f'Pedido {order.external_id}: {result}')
            except ProviderError:
                tally['ERROR'] += 1
                self.stderr.write(f'Pedido {order.external_id}: falha na consulta/validação, sem dados sensíveis.')
        self.stdout.write('Resumo: ' + ', '.join(f'{key}={value}' for key, value in tally.items()))
        self.stdout.write('Sem Order, KDS, webhook ou comandos remotos de alteração.')
