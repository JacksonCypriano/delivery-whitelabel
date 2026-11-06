"""Read-only, safe 99Food readiness check for HML."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from apps.channels.models import Connection, ExternalOrder
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Mostra vínculos sandbox e bloqueios operacionais sem expor credenciais."

    def add_arguments(self, parser):
        parser.add_argument('--tenant-slug', required=True)
        parser.add_argument('--app-shop-id', required=True)
        parser.add_argument('--shop-id', required=True)

    def handle(self, *args, **opts):
        tenant = Tenant.objects.filter(slug=opts['tenant_slug']).first()
        if tenant is None:
            raise CommandError('Tenant não encontrado.')
        if opts['app_shop_id'] != 'vdd-' + tenant.slug:
            raise CommandError('AppShopID não corresponde ao tenant.')
        connections = Connection.objects.filter(provider='99food', mode='test', merchant_id=opts['shop_id'])
        if connections.filter(tenant_id__isnull=False).exclude(tenant_id=tenant.pk).exists():
            raise CommandError('Loja 99Food vinculada a outro tenant.')
        connection = connections.first()
        count = ExternalOrder.objects.filter(connection=connection).count() if connection else 0
        enabled = bool(getattr(settings, 'FOOD99_SANDBOX_ENABLED', False))
        self.stdout.write('tenant=%s; conexao=%s; pedidos_importados=%s; sandbox=%s' % (
            tenant.slug, 'vinculada' if connection else 'ainda_nao_vinculada',
            count, 'habilitado' if enabled else 'desabilitado'))
        self.stdout.write('webhook=POST_BLOQUEADO; status_922=NAO_HOMOLOGADO; operacoes_remotas=NAO_HABILITADAS')
        self.stdout.write('Próximo passo: obter contrato de webhook e estados; NÃO liberar importação em Order ainda.')
