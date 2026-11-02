"""Read-only inspection of 99Food order schema; deliberately excludes personal data."""
import json
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_orders import get_order_detail
from apps.channels.food99_mapping_probe import inspect_order


class Command(BaseCommand):
    help = 'Confere formato do pedido 99Food sem imprimir dados pessoais nem persistir pedidos.'

    def add_arguments(self, parser):
        parser.add_argument('--app-shop-id', required=True)
        parser.add_argument('--shop-id', required=True)
        parser.add_argument('--order-id', required=True)
        parser.add_argument('--execute', action='store_true')

    def handle(self, *args, **options):
        if not options['execute']:
            self.stdout.write('Modo seguro: adicione --execute para consultar a API sandbox.')
            return
        try:
            data = get_order_detail(options['app_shop_id'], options['order_id'])
            summary = inspect_order(data, order_id=options['order_id'], app_shop_id=options['app_shop_id'], shop_id=options['shop_id'])
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(json.dumps(summary, indent=2, ensure_ascii=False))
        self.stdout.write(self.style.SUCCESS('Inspeção concluída: nenhum pedido foi gravado.'))
