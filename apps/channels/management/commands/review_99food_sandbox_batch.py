"""Batch inspection / explicitly reviewed sandbox import; never triggers remote order actions."""
import csv
import io
import re
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_orders import get_order_detail
from apps.channels.food99_import import preview, import_reviewed, fingerprint_preview
from apps.channels.models import Connection, ExternalOrder

SAFE_IDS = re.compile(r"^[0-9]{1,30}$")


def parse_order_ids(raw):
    ids = [part.strip() for part in raw.split(',')]
    if not ids or len(ids) > 50 or any(not SAFE_IDS.fullmatch(x) for x in ids):
        raise CommandError('Informe entre 1 e 50 IDs numéricos válidos separados por vírgula.')
    if len(ids) != len(set(ids)):
        raise CommandError('Lista contém IDs de pedido duplicados.')
    return ids


def compare_existing(*, shop_id, order_id, tenant_id, fingerprint):
    connection = Connection.objects.filter(provider='99food', mode='test', merchant_id=str(shop_id)).first()
    if connection is not None and tenant_id is not None and connection.tenant_id != tenant_id:
        raise CommandError('Conexão 99Food pertence a outro tenant.')
    if connection is None:
        return 'novo'
    existing = ExternalOrder.objects.filter(connection=connection, external_id=str(order_id)).select_related('order').first()
    if existing is None:
        return 'novo'
    if existing.order.tenant_id != connection.tenant_id or existing.order.source != '99food':
        raise CommandError('Pedido previamente associado a tenant ou canal incompatível.')
    if tenant_id is not None and existing.order.tenant_id != tenant_id:
        raise CommandError('Pedido já importado pertence a outro tenant.')
    return 'igual' if (existing.financials or {}).get('snapshot_fingerprint') == fingerprint else 'divergente'


class Command(BaseCommand):
    help = 'Consulta e audita até 50 pedidos do sandbox 99Food; grava somente com revisão explícita.'

    def add_arguments(self, parser):
        parser.add_argument('--app-shop-id', required=True)
        parser.add_argument('--shop-id', required=True)
        parser.add_argument('--order-ids', required=True, help='IDs separados por vírgula (máximo 50)')
        parser.add_argument('--tenant-id', type=int)
        parser.add_argument('--commit', action='store_true')
        parser.add_argument('--confirm-currency-brl', action='store_true')
        parser.add_argument('--import-pending-for-review', action='store_true')

    def handle(self, *args, **opts):
        ids = parse_order_ids(opts['order_ids'])
        if not SAFE_IDS.fullmatch(str(opts['shop_id'])):
            raise CommandError('ID da loja 99Food inválido.')
        if opts['commit'] and (not opts['tenant_id'] or not opts['confirm_currency_brl'] or not opts['import_pending_for_review']):
            raise CommandError('Gravação requer --tenant-id, --confirm-currency-brl e --import-pending-for-review.')
        if opts['tenant_id'] is not None:
            from apps.tenants.models import Tenant
            if not Tenant.objects.filter(pk=opts['tenant_id']).exists():
                raise CommandError('Tenant informado não encontrado.')
        results=[]
        for order_id in ids:
            try:
                detail=get_order_detail(opts['app_shop_id'],order_id)
                data=preview(detail,app_shop_id=opts['app_shop_id'],shop_id=opts['shop_id'],order_id=order_id)
                comparison=compare_existing(shop_id=opts['shop_id'],order_id=order_id,
                    tenant_id=opts['tenant_id'],fingerprint=fingerprint_preview(data))
                if comparison=='divergente':
                    state='REVISAR_DIVERGENCIA'
                elif opts['commit'] and comparison=='novo':
                    pk,created=import_reviewed(detail,tenant_id=opts['tenant_id'],app_shop_id=opts['app_shop_id'],
                        shop_id=opts['shop_id'],order_id=order_id,currency='BRL',status_override='pending')
                    state='IMPORTADO_EM_REVISAO' if created else 'EXISTENTE'
                else:
                    state={'novo':'VALIDADO_NAO_GRAVADO','igual':'EXISTENTE','divergente':'REVISAR_DIVERGENCIA'}[comparison]
                results.append((order_id,state,len(data['items']),data['status_code']))
            except ProviderError:
                results.append((order_id,'ERRO_VALIDACAO',0,'-'))
            except CommandError:
                raise
        output=io.StringIO()
        writer=csv.writer(output)
        writer.writerow(('order_id','resultado','itens','status_externo'))
        writer.writerows(results)
        self.stdout.write(output.getvalue().rstrip())
        self.stdout.write('Nenhuma ação remota executada. Status externo não homologado; pedidos importados requerem revisão.')
        if any(r[1] in ('ERRO_VALIDACAO','REVISAR_DIVERGENCIA') for r in results):
            raise CommandError('Há pedidos que exigem revisão; consulte o resumo sem dados pessoais acima.')
