"""Safe manual sandbox import; no client PII printed."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_orders import get_order_detail
from apps.channels.food99_import import preview, import_reviewed


class Command(BaseCommand):
    help='Inspeciona ou importa, sob confirmação explícita, pedido 99Food sandbox.'

    def add_arguments(self, parser):
        parser.add_argument('--app-shop-id',required=True)
        parser.add_argument('--shop-id',required=True)
        parser.add_argument('--order-id',required=True)
        parser.add_argument('--tenant-id',type=int)
        parser.add_argument('--commit',action='store_true')
        parser.add_argument('--confirm-currency-brl',action='store_true')
        parser.add_argument('--import-pending-for-review',action='store_true')

    def handle(self,*args,**opts):
        if opts['commit'] and (not opts['tenant_id'] or not opts['confirm_currency_brl'] or not opts['import_pending_for_review']):
            raise CommandError('Para gravar: --tenant-id, --confirm-currency-brl e --import-pending-for-review são obrigatórios.')
        try:
            detail=get_order_detail(opts['app_shop_id'],opts['order_id'])
            data=preview(detail,app_shop_id=opts['app_shop_id'],shop_id=opts['shop_id'],order_id=opts['order_id'])
            self.stdout.write(f"Validado: pedido={data['order_id']}, itens={len(data['items'])}, status_externo={data['status_code']}, valor_menor_unidade=convertido, modo={'gravação' if opts['commit'] else 'leitura'}")
            if not opts['commit']:
                self.stdout.write('Nenhum registro gravado. Status e moeda dependem de confirmação explícita.')
                return
            order_pk,created=import_reviewed(detail,tenant_id=opts['tenant_id'],app_shop_id=opts['app_shop_id'],
                 shop_id=opts['shop_id'],order_id=opts['order_id'],currency='BRL',status_override='pending')
            self.stdout.write(self.style.SUCCESS(f'Pedido local #{order_pk}; criado={created}; revisão operacional obrigatória.'))
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
