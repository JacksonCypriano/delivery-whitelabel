"""Persist a reviewed 99Food snapshot in quarantine, not the operational order table."""
from django.core.management.base import BaseCommand, CommandError
from apps.tenants.models import Tenant
from apps.channels.connectors import ProviderError
from apps.channels.food99_orders import get_order_detail
from apps.channels.food99_staging import stage_order
from apps.channels.food99_import import preview


class Command(BaseCommand):
    help = 'Consulta e armazena pedido 99Food numa quarentena separada (não aparece no KDS).'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-slug', required=True)
        parser.add_argument('--app-shop-id', required=True)
        parser.add_argument('--shop-id', required=True)
        parser.add_argument('--order-id', required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **opts):
        tenant = Tenant.objects.filter(slug=opts['tenant_slug']).first()
        if tenant is None:
            raise CommandError('Tenant não encontrado.')
        try:
            detail = get_order_detail(opts['app_shop_id'], opts['order_id'])
            info = preview(detail, app_shop_id=opts['app_shop_id'],
                           shop_id=opts['shop_id'], order_id=opts['order_id'])
            if not opts['apply']:
                self.stdout.write('VALIDADO_SEM_GRAVAR: itens=%s; status=%s' %
                                  (len(info['items']), info['status_code']))
                return
            _, result = stage_order(detail, tenant=tenant, app_shop_id=opts['app_shop_id'],
                                    shop_id=opts['shop_id'], order_id=opts['order_id'])
            self.stdout.write(result + '; sem Order/KDS/webhook/ações remotas.')
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
