import json
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from rest_framework.response import Response
from apps.merchant.api import MerchantAPI
from .models import Connection,ExternalOrder,Inbox,Outbox
from .connectors import connector,ProviderError,valid_ifood_signature
from .services import receive

@csrf_exempt
@require_POST
def ifood_webhook(request,mode):
    if mode not in ('test','live') or not settings.CHANNELS_NETWORK_ENABLED or (mode=='live' and not settings.CHANNELS_LIVE_ENABLED):return JsonResponse({'detail':'Indisponível.'},status=404)
    if len(request.body)>131072:return JsonResponse({'detail':'Evento muito grande.'},status=413)
    if not valid_ifood_signature(request.body,request.headers.get('X-IFood-Signature',''),mode):return JsonResponse({'detail':'Assinatura inválida.'},status=401)
    try:
        data=json.loads(request.body)
        if not isinstance(data,dict):raise ValueError
        conn=Connection.objects.filter(provider='ifood',mode=mode,merchant_id=str(data.get('merchantId','')),enabled=True).first()
        if conn is None:return JsonResponse({'detail':'Estabelecimento não vinculado.'},status=404)
        receive(conn,data)
    except (ValueError,ProviderError):return JsonResponse({'detail':'Evento inválido.'},status=400)
    return JsonResponse({'received':True},status=202)

class Integrations(MerchantAPI):
    def get(self,request):
        data=[]
        for provider,label in [('ifood','iFood'),('99food','99Food')]:
            connections=[]
            for c in Connection.objects.filter(tenant=request.tenant,provider=provider).order_by('pk'):
                connections.append({'id':c.pk,'merchant_id':c.merchant_id,'merchant_name':c.merchant_name,'mode':c.mode,'enabled':c.enabled,'status':c.status,'last_sync':c.last_sync,'error':c.last_error,'pending_events':c.events.filter(state__in=['pending','processing','error','blocked']).count()})
            data.append({'provider':provider,'label':label,'blocked':provider=='99food','connections':connections})
        return Response({'providers':data})
    @transaction.atomic
    def post(self,request):
        provider=request.data.get('provider')
        if provider not in ('ifood','99food'):return Response({'detail':'Plataforma inválida.'},status=400)
        action=request.data.get('action')
        if action=='request':
            # Merchant cannot claim another store under global integrator credentials.
            c,_=Connection.objects.get_or_create(tenant=request.tenant,provider=provider,merchant_id=f'request-{request.tenant.pk}',mode='test')
            if not c.enabled:
                c.status='awaiting_authorization';c.save(update_fields=['status'])
            return Response({'detail':'Solicitação registrada. A equipe vinculará o estabelecimento após conferir a autorização no portal.'})
        c=Connection.objects.select_for_update().filter(pk=request.data.get('id'),tenant=request.tenant,provider=provider).first()
        if c is None:return Response({'detail':'Conexão não encontrada.'},status=404)
        if action=='disconnect':
            c.enabled=False;c.status='not_configured';c.save(update_fields=['enabled','status'])
            return Response({'detail':'Desconectado localmente. Histórico preservado. Revogue também o acesso no portal da plataforma.'})
        return Response({'detail':'Ação inválida.'},status=400)

class CancellationReasons(MerchantAPI):
    def get(self,request,pk):
        x=ExternalOrder.objects.select_related('connection').filter(order_id=pk,order__tenant=request.tenant).first()
        if x is None:return Response({'detail':'Pedido não encontrado.'},status=404)
        if not x.connection.enabled:return Response({'detail':'Integração desconectada.'},status=400)
        if x.connection.mode=='simulation':return Response({'reasons':[{'code':'SIM','description':'Cancelamento de teste local'}]})
        try:return Response({'reasons':connector(x.connection).reasons(x.external_id)})
        except ProviderError as exc:return Response({'detail':str(exc)},status=503)

class IntegrationEvents(MerchantAPI):
    def get(self, request):
        from apps.merchant.pagination import paginate, metadata
        page=paginate(Inbox.objects.filter(connection__tenant=request.tenant).select_related('connection').order_by('-received_at','-pk'),request)
        return Response({'events':[{'id':e.pk,'provider':e.connection.provider,'order_id':e.order_id,'code':e.code,'state':e.state,'attempts':e.attempts,'error':e.error,'received_at':e.received_at} for e in page], 'pagination':metadata(page)})
