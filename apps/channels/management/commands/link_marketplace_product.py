from django.core.management.base import BaseCommand, CommandError
from apps.channels.models import Connection,ProductLink
from apps.stores.models import Product

class Command(BaseCommand):
    help='Vincula o externalCode a um produto de estoque da mesma loja. Não recalcula o preço externo.'
    def add_arguments(self,p):
        p.add_argument('--tenant',required=True)
        p.add_argument('--connection',required=True,type=int)
        p.add_argument('--external-code',required=True)
        p.add_argument('--product',required=True,type=int)
    def handle(self,*args,**o):
        c=Connection.objects.filter(pk=o['connection'],tenant__slug=o['tenant']).first()
        p=Product.objects.filter(pk=o['product'],tenant__slug=o['tenant']).first()
        if not c or not p or not 0<len(o['external_code'])<=128:raise CommandError('Conexão/produto/código inválidos para esta loja.')
        ProductLink.objects.update_or_create(connection=c,external_code=o['external_code'],defaults={'product':p})
        self.stdout.write('Vínculo salvo. Será usado nas próximas movimentações, sem débito retroativo.')
