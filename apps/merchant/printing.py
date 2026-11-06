import hashlib
import json
import secrets
import uuid
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from apps.orders.printing_models import PrintDevice, PrintJob
from apps.orders.printing import enqueue, TEMPLATES
from .api import MerchantAPI
from .orders import _base_queryset


class Printing(MerchantAPI):
    def get(self,request):
        device,_=PrintDevice.objects.get_or_create(tenant=request.tenant)
        return Response({'device':{k:getattr(device,k) for k in ['name','active','paper_mm','copies','templates','auto_enabled','trigger','last_seen']},'jobs':list(PrintJob.objects.filter(device=device).order_by('-created_at').values('id','order_id','template','state','created_at','reprint_of_id')[:100])})

    @transaction.atomic
    def post(self,request):
        device,_=PrintDevice.objects.get_or_create(tenant=request.tenant)
        device=PrintDevice.objects.select_for_update().get(pk=device.pk)
        data=request.data;action=data.get('action')
        try:
            if action=='pair':
                token=secrets.token_urlsafe(32)
                device.token_hash=hashlib.sha256(token.encode()).hexdigest();device.active=True;device.save()
                return Response({'token':token,'detail':'Copie o token para o agente local. Ele não será exibido novamente.'})
            if action=='revoke':
                device.active=False;device.auto_enabled=False;device.token_hash='';device.save()
            elif action=='settings':
                width=int(data.get('paper_mm',80));copies=int(data.get('copies',1));templates=data.get('templates',[])
                if width not in {58,80} or not 1<=copies<=3 or not isinstance(templates,list) or not set(templates)<=set(TEMPLATES): raise ValueError('Configuração inválida.')
                if data.get('trigger') not in {'pending','confirmed','preparing','ready','ready_for_pickup'}: raise ValueError('Evento inválido.')
                device.name=str(data.get('name','Balcão'))[:100];device.paper_mm=width;device.copies=copies;device.templates=list(set(templates));device.trigger=data['trigger'];device.auto_enabled=data.get('auto_enabled') is True;device.save()
            elif action in {'print','reprint'}:
                original=None
                if action=='reprint':
                    original=PrintJob.objects.filter(device=device,pk=uuid.UUID(str(data.get('job')))).first()
                    if not original: return Response({'detail':'Via não encontrada.'},status=404)
                    order_id=original.order_id;template=original.template
                else: order_id=int(data.get('order'));template=data.get('template','full')
                order=_base_queryset(request.tenant).filter(pk=order_id).first()
                if not order: return Response({'detail':'Pedido não encontrado.'},status=404)
                # Client request id makes repeat clicks/retries idempotent.
                key=str(uuid.UUID(str(data.get('request_id'))))
                job=enqueue(device,order,template,key,original)
                return Response({'detail':'Impressão solicitada. Acompanhe a fila; isto não confirma saída do papel.','job':str(job.pk),'text':job.text})
            else: raise ValueError('Ação inválida.')
        except (ValueError,TypeError): return Response({'detail':'Confira dispositivo, pedido, formato e identificador da solicitação.'},status=400)
        return Response({'detail':'Configuração de impressão salva.'})


@csrf_exempt
def device_queue(request):
    if request.method!='POST': return JsonResponse({'detail':'POST required'},status=405)
    auth=request.headers.get('Authorization','')
    if not auth.startswith('Bearer ') or len(auth)>200: return JsonResponse({'detail':'Unauthorized'},status=401)
    digest=hashlib.sha256(auth[7:].encode()).hexdigest()
    if len(request.body)>4000: return JsonResponse({'detail':'Too large'},status=413)
    try:
        data=json.loads(request.body or '{}')
        if not isinstance(data,dict): raise ValueError()
        with transaction.atomic():
            device=PrintDevice.objects.select_for_update().filter(token_hash=digest,active=True).first()
            if device is None: return JsonResponse({'detail':'Unauthorized'},status=401)
            # Pair tokens cannot be moved across tenant domains.
            if getattr(request,'tenant',None)!=device.tenant: return JsonResponse({'detail':'Wrong store'},status=403)
            device.last_seen=timezone.now();device.save(update_fields=['last_seen'])
            if data.get('action')=='ack':
                if data.get('state') not in {'spooled','uncertain','failed'}: raise ValueError()
                job=PrintJob.objects.select_for_update().filter(device=device,pk=uuid.UUID(str(data.get('job')))).first()
                if not job: return JsonResponse({'detail':'Not found'},status=404)
                if job.state=='claimed': job.state=data['state'];job.save()
                return JsonResponse({'state':job.state})
            if data.get('action')!='claim': raise ValueError()
            job=PrintJob.objects.select_for_update().filter(device=device,state='queued').order_by('created_at').first()
            if not job: return JsonResponse({'job':None})
            job.state='claimed';job.save()
            return JsonResponse({'job':{'id':str(job.pk),'text':job.text,'paper_mm':job.paper_mm,'copies':job.copies}})
    except (ValueError,TypeError): return JsonResponse({'detail':'Invalid request'},status=400)
