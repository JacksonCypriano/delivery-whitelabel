from django.core.management.base import BaseCommand, CommandError
from apps.tenants.models import Tenant
from apps.channels.simulator import simulate, require_simulator

class Command(BaseCommand):
    help='Cria pedidos fictícios persistentes para Pedidos Ativos e KDS; nenhuma chamada externa.'
    def add_arguments(self,p):
        p.add_argument('--tenant',required=True)
        p.add_argument('--provider',choices=['ifood','99food','all'],default='all')
        p.add_argument('--order-key',default='demo-1')
        p.add_argument('--event',choices=['PLACED','CONFIRMED','PREPARATION_STARTED','READY_TO_PICKUP','DISPATCHED','CONCLUDED','CANCELLED'],default='PLACED')
        p.add_argument('--pickup',action='store_true')
        p.add_argument('--payment-due',action='store_true')
        p.add_argument('--scheduled',help='Data ISO 8601 com fuso, por exemplo 2026-12-01T18:00:00-03:00')
    def handle(self,*args,**o):
        require_simulator()
        try:tenant=Tenant.objects.get(slug=o['tenant'])
        except Tenant.DoesNotExist:raise CommandError('Loja não encontrada.')
        providers=['ifood','99food'] if o['provider']=='all' else [o['provider']]
        for provider in providers:
            x=simulate(tenant,provider,o['order_key'],o['event'],pickup=o['pickup'],paid=not o['payment_due'],scheduled=o['scheduled'])
            self.stdout.write(self.style.SUCCESS(f'SIMULAÇÃO {provider}: pedido interno #{x.order_id}, externo {x.external_id}.'))
