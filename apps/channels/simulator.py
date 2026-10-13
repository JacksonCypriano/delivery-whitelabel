"""Local INTERNAL DTO fixtures, deliberately not a 99Food wire contract."""
from django.conf import settings
from django.core.management.base import CommandError
from django.utils import timezone
from .models import Connection
from .services import receive, apply_event

def require_simulator():
    if not settings.CHANNELS_SIMULATOR_ENABLED or str(getattr(settings,'SETTINGS_MODULE','')).endswith('.prod'):
        raise CommandError('Simulador permitido somente em homologação, com CHANNELS_SIMULATOR_ENABLED=1.')

def sample(connection, key='demo-1', pickup=False, paid=True, scheduled=None):
    return {'financials':{'prepaid':('44.90' if pickup else '49.90') if paid else '0.00','pending':'0.00' if paid else ('44.90' if pickup else '49.90'),'additional_fees':'0.00'},'external_id':key,'merchant_id':connection.merchant_id,'display_id':key,'customer_name':'Cliente fictício · SIMULAÇÃO','created_at':timezone.now().isoformat(),'scheduled_for':scheduled,'delivery_type':'pickup' if pickup else 'delivery','delivery_by':'MERCHANT','paid':paid,'payment_summary':'Pagamento fictício antecipado' if paid else 'Dinheiro fictício na entrega','total':'44.90' if pickup else '49.90','subtotal':'44.90','delivery_fee':'0.00' if pickup else '5.00','discount':'0.00','items':[{'code':'DEMO-LANCHE','name':'Combo de demonstração','price':'44.90','quantity':1,'notes':'Sem cebola · pedido fictício','details':{'customizations':[{'option_name':'Batata grande','price':'5.00'}], 'external_line_total':'44.90'}}],'address':{'delivery_street':'Rua de demonstração','delivery_number':'100','delivery_city':'Cidade teste','delivery_state':'SP'}}

def simulate(tenant, provider, key='demo-1', code='PLACED', **kwargs):
    require_simulator()
    conn,_=Connection.objects.get_or_create(tenant=tenant,provider=provider,mode='simulation',merchant_id=f'simulation-{tenant.pk}-{provider}',defaults={'merchant_name':tenant.name+' · simulação','enabled':True,'status':'connected'})
    if not conn.enabled:raise CommandError('Simulação desconectada. Use outra base de homologação ou reative por administração técnica.')
    dto=sample(conn,key,**kwargs)
    event=receive(conn,{'id':f'{key}:{code}','orderId':key,'merchantId':conn.merchant_id,'code':code,'createdAt':timezone.now().isoformat()})
    apply_event(event.pk,normalized=dto)
    return conn.orders.get(external_id=key)
