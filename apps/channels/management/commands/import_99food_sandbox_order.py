"""Safe manual sandbox import; no client PII printed."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.models import Connection, ExternalOrder
from apps.channels.connectors import ProviderError
from apps.channels.food99_orders import get_order_detail
from apps.channels.food99_import import preview, import_reviewed, fingerprint_preview


class Command(BaseCommand):
    help='Inspeciona ou importa, sob confirmação explícita, pedido 99Food sandbox.'

    def add_arguments(self, parser):
        parser.add_argument('--app-shop-id',required=True)
        parser.add_argument('--shop-id',required=True)
        parser.add_argument('--order-id',required=True)
        parser.add_argument('--tenant-id',type=int)
        parser.add_argument('--audit-existing',action='store_true',help='Compara pedido já importado sem alterar dados.')
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
            if opts['audit_existing']:
                conn=Connection.objects.filter(provider='99food', mode='test', merchant_id=str(opts['shop_id'])).first()
                existing=(ExternalOrder.objects.filter(connection=conn, external_id=str(opts['order_id']))
                          .select_related('order').first()) if conn else None
                if existing:
                    print_equal=existing.financials.get('snapshot_fingerprint') == fingerprint_preview(data)
                    self.stdout.write('Auditoria local: existente=sim, tenant_id=%s, igualdade_financeira_e_itens=%s' %
                                      (existing.order.tenant_id, 'sim' if print_equal else 'não'))
                    if not print_equal:
                        self.stdout.write(self.style.WARNING('Divergência detectada; pedido preservado, revisão manual necessária.'))
                else:
                    self.stdout.write('Auditoria local: existente=não; nenhum pedido gravado.')
                return
            if not opts['commit']:
                self.stdout.write('Nenhum registro gravado. Status e moeda dependem de confirmação explícita.')
                return
            order_pk,created=import_reviewed(detail,tenant_id=opts['tenant_id'],app_shop_id=opts['app_shop_id'],
                 shop_id=opts['shop_id'],order_id=opts['order_id'],currency='BRL',status_override='pending')
            self.stdout.write(self.style.SUCCESS(f'Pedido local #{order_pk}; criado={created}; revisão operacional obrigatória.'))
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
