from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.tenants.models import Tenant
from apps.channels.models import Connection
from apps.channels.connectors import IFood,ProviderError

class Command(BaseCommand):
    help='Vinculação administrativa após autorização centralizada e conferência de propriedade. Não recebe segredos via argumentos.'
    def add_arguments(self,p):
        p.add_argument('--tenant',required=True)
        p.add_argument('--provider',choices=['ifood','99food'],required=True)
        p.add_argument('--merchant-id',required=True)
        p.add_argument('--mode',choices=['test','live'],default='test')
        p.add_argument('--confirm-ownership',action='store_true',help='Operador conferiu que o estabelecimento autorizado pertence a este tenant.')
    def handle(self,*args,**o):
        if not o['confirm_ownership']:raise CommandError('Confira a propriedade da loja e informe --confirm-ownership. A autorização global não comprova a propriedade do tenant.')
        if o['provider']=='99food':raise CommandError('99Food bloqueado: contrato oficial e homologação pendentes.')
        if o['mode']=='test' and str(getattr(settings,'SETTINGS_MODULE','')).endswith('.prod'):raise CommandError('Use o ambiente de homologação para conectar aplicativos de teste.')
        try:
            tenant=Tenant.objects.get(slug=o['tenant'])
            rows=IFood(o['mode']).merchants()
            merchant=next((m for m in rows if str(m['id'])==o['merchant_id']),None)
            if not merchant:raise CommandError('Estabelecimento não autorizado para este aplicativo.')
            with transaction.atomic():
                c,_=Connection.objects.get_or_create(provider='ifood',mode=o['mode'],merchant_id=o['merchant_id'],defaults={'tenant':tenant})
                c=Connection.objects.select_for_update().get(pk=c.pk)
                if c.tenant_id!=tenant.pk:raise CommandError('Estabelecimento já vinculado a outra loja. Não será transferido.')
                c.merchant_name=str(merchant.get('name',''))[:180];c.enabled=True;c.status='connected';c.last_error='';c.save()
                Connection.objects.filter(tenant=tenant,provider='ifood',merchant_id=f'request-{tenant.pk}').update(status='not_configured')
        except Tenant.DoesNotExist:raise CommandError('Loja não encontrada.')
        except ProviderError as exc:raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f'Vínculo {c.pk} verificado. Eventos serão recebidos pelo worker/beat.'))
