import json
import re
import secrets
from urllib.parse import quote, urlsplit
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from apps.superpanel.api import SuperAdminAPI
from apps.integrations.whatsapp_agent.client import TenantEvolutionClient
from apps.integrations.whatsapp_agent.provider import extract_message, extract_qr, normalize_event_name
from .commercial import validate_instance, receive, articles
from .commercial_catalog import catalog, published_catalog
from .commercial_models import CommercialControl, CommercialConversation, CommercialMessage, CommercialArticle, CommercialAudit, CommercialPilotContact, CommercialHandoffAlert, CommercialOtpExclusion
from .commercial_pilot import normalize_phone, otp_excluded


@csrf_exempt
def commercial_webhook(request):
    token = getattr(settings,'COMMERCIAL_AGENT_WEBHOOK_TOKEN','')
    if request.method!='POST': return JsonResponse({'detail':'POST required'},status=405)
    if len(token)<32 or not constant_time_compare(request.headers.get('X-VDD-Commercial-Token',''),token):
        return JsonResponse({'detail':'Unauthorized'},status=401)
    if len(request.body)>64000: return JsonResponse({'detail':'Too large'},status=413)
    try:
        payload=json.loads(request.body)
        if not isinstance(payload,dict): raise ValueError()
        control=CommercialControl.current()
        if payload.get('instance') != control.instance or not control.instance:
            return JsonResponse({'detail':'Unknown instance'},status=404)
        if normalize_event_name(payload.get('event'))!='messages.upsert':
            return JsonResponse({'accepted':False})
        raw=payload.get('data')
        # Do not interpret sync/history batches as fresh customer intent.
        if not isinstance(raw,dict): return JsonResponse({'accepted':False})
        key=raw.get('key') or {}
        remote=str(key.get('remoteJidAlt') or key.get('remoteJid') or '') if isinstance(key,dict) else ''
        if not remote.endswith('@s.whatsapp.net'): return JsonResponse({'accepted':False})
        message=extract_message(raw)
        if message is None: return JsonResponse({'accepted':False})
        receive(control.instance,message)
        return JsonResponse({'accepted':True})
    except (ValueError,TypeError):
        return JsonResponse({'detail':'Invalid event'},status=400)


def webhook_config():
    url=getattr(settings,'COMMERCIAL_AGENT_WEBHOOK_URL','')
    token=getattr(settings,'COMMERCIAL_AGENT_WEBHOOK_TOKEN','')
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment or len(token)<32:
        raise ValueError('Configure URL HTTPS e segredo do callback comercial no servidor.')
    return {'enabled':True,'url':url,'headers':{'X-VDD-Commercial-Token':token},'byEvents':False,'base64':False,'events':['MESSAGES_UPSERT']}


class CommercialPanel(SuperAdminAPI):
    def get(self,request):
        control=CommercialControl.current()
        conversations=CommercialConversation.objects.all().order_by('-updated_at')
        term=str(request.query_params.get('q',''))[:80]
        if term:
            from django.db.models import Q
            conversations=conversations.filter(Q(phone__icontains=term)|Q(name__icontains=term))
        if request.query_params.get('paused')=='1': conversations=conversations.filter(paused=True)
        from apps.merchant.pagination import paginate,metadata
        page=paginate(conversations,request)
        selected=None
        raw_id=request.query_params.get('conversation','')
        if str(raw_id).isdigit():
            c=CommercialConversation.objects.filter(pk=raw_id).first()
            if c:
                selected={'id':c.pk,'phone':c.phone,'name':c.name,'notes':c.notes,'stage':c.stage,'paused':c.paused,'opted_out':c.opted_out,'reason':c.reason,'messages':list(c.messages.order_by('-pk').values('id','text','reply','from_me','state','created_at')[:100])[::-1]}
        result=catalog()
        pilot=list(CommercialPilotContact.objects.filter(active=True).order_by('phone').values('phone','created_at'))
        alerts=list(CommercialHandoffAlert.objects.filter(state='pending').order_by('-created_at').values('id','conversation_id','reason','created_at')[:30])
        return Response({'pilot':{'restricted':True,'allowed':pilot,'alerts':alerts,'pending_count':CommercialHandoffAlert.objects.filter(state='pending').count(),'otp_excluded_count':CommercialOtpExclusion.objects.filter(instance=control.instance).count()},'control':{'instance':control.instance,'enabled':control.enabled,'server_enabled':getattr(settings,'COMMERCIAL_AGENT_ENABLED',False),'demo_url':control.demo_url,'contact_url':control.contact_url},
            'catalog':result,'published':result['valid'] and result['fingerprint']==control.catalog_fingerprint,
            'articles':[{'id':a.pk,'slug':a.slug,'version':a.version,'title':a.title,'body':a.body,'source_url':a.source_url,'published':a.published} for a in articles(include_drafts=True)],
            'conversations':list(page.object_list.values('id','phone','name','stage','source','paused','reason','updated_at')),'pagination':metadata(page),'selected':selected,
            'metrics':list(CommercialConversation.objects.values('stage').annotate(count=Count('id'))),
            'events':list(CommercialAudit.objects.order_by('-pk').values('action','created_at','conversation_id')[:30])})

    @transaction.atomic
    def post(self,request):
        control=CommercialControl.current()
        control=CommercialControl.objects.select_for_update().get(pk=control.pk)
        action=request.data.get('action')
        client=TenantEvolutionClient()
        try:
            if action=='publish_catalog':
                result=catalog()
                if not result['valid'] or request.data.get('fingerprint')!=result['fingerprint']:
                    raise ValueError('Catálogo divergente ou alterado. Revise os planos oficiais antes de publicar.')
                control.catalog_fingerprint=result['fingerprint'];control.catalog_reviewed_at=timezone.now();control.save()
            elif action in {'enable','pause'}:
                if action=='enable':
                    if request.data.get('confirm_pilot') is not True: raise ValueError('Confirme explicitamente o piloto restrito.')
                    if not getattr(settings,'COMMERCIAL_AGENT_ENABLED',False): raise ValueError('Ativação no servidor ainda não autorizada/configurada.')
                    validate_instance(control.instance);published_catalog(control)
                    if not articles(): raise ValueError('Publique ao menos um artigo revisado.')
                    if client.status(control.instance)!='open': raise ValueError('Conecte a instância primeiro.')
                    if not CommercialPilotContact.objects.filter(active=True).exists(): raise ValueError('Cadastre um contato autorizado antes de iniciar o piloto.')
                if action == 'pause' or not control.enabled:
                    CommercialMessage.objects.filter(state='queued').update(state='held')
                control.enabled=action=='enable';control.save()
            elif action in {'pilot_allow','pilot_revoke'}:
                if control.enabled:
                    raise ValueError('Pause o agente antes de alterar a lista do piloto.')
                number=normalize_phone(request.data.get('phone'))
                if action=='pilot_allow':
                    if otp_excluded(number, control.instance): raise ValueError('Contato usado para OTP; não pode ser autorizado como lead comercial.')
                    row,_=CommercialPilotContact.objects.get_or_create(phone=number,defaults={'author':request.user})
                    if not row.active:
                        row.active=True;row.author=request.user;row.save(update_fields=['active','author','updated_at'])
                else:
                    CommercialPilotContact.objects.filter(phone=number).update(active=False)
            elif action=='instances':
                data=client._request('GET','instance/fetchInstances')
                if not isinstance(data,list): raise ValueError('Resposta incompatível da Evolution.')
                names=[]
                for item in data:
                    if not isinstance(item,dict): continue
                    row=item.get('instance',item)
                    if not isinstance(row,dict): continue
                    name=row.get('instanceName') or row.get('name')
                    try: names.append(validate_instance(name))
                    except ValueError: continue
                return Response({'instances':names})
            elif action in {'bind','create'}:
                if control.enabled: raise ValueError('Pause o agente antes de trocar a instância.')
                name=validate_instance(request.data.get('instance',''))
                hook=webhook_config()
                if action=='create':
                    client._request('POST','instance/create',{'instanceName':name,'token':secrets.token_hex(24),'integration':'WHATSAPP-BAILEYS','qrcode':True,'groupsIgnore':True,'syncFullHistory':False,'webhook':hook})
                else:
                    client.status(name)
                    client._request('POST',f'webhook/set/{quote(name,safe="")}',{'webhook':hook})
                control.instance=name;control.save()
            elif action in {'status','connect','restart','logout','rotate_webhook'}:
                validate_instance(control.instance)
                if action=='status': return Response({'connection':client.status(control.instance)})
                if action=='connect': return Response({'qr':extract_qr(client.connect(control.instance))})
                if action=='restart': client.restart(control.instance)
                if action=='logout':
                    control.enabled=False;control.save();client.logout(control.instance)
                if action=='rotate_webhook':
                    client._request('POST',f'webhook/set/{quote(control.instance,safe="")}',{'webhook':webhook_config()})
            elif action=='article':
                slug=str(request.data.get('slug',''))
                title=str(request.data.get('title','')).strip()
                body=str(request.data.get('body','')).strip()
                source=str(request.data.get('source_url',''))
                if not re.fullmatch(r'[a-z0-9-]{1,80}',slug) or not title or len(title)>160 or not body or len(body)>1100:
                    raise ValueError('Informe slug, título e conteúdo de até 1100 caracteres.')
                if re.search(r'R\$|\d+[.,]\d{2}|https?://',body,re.I):
                    raise ValueError('Preços e links devem vir do catálogo/configuração, não do artigo.')
                if source and (urlsplit(source).scheme!='https' or not urlsplit(source).hostname): raise ValueError('Fonte deve usar HTTPS.')
                from types import SimpleNamespace
                from .commercial_copy import units
                units(SimpleNamespace(pk=0, version=0, slug=slug, body=body))
                version=(CommercialArticle.objects.filter(slug=slug).aggregate(n=Max('version'))['n'] or 0)+1
                CommercialArticle.objects.create(slug=slug,version=version,title=title,body=body,source_url=source,published=request.data.get('published') is True,author=request.user)
            elif action in {'takeover','resume','lead'}:
                raw=request.data.get('conversation')
                if not str(raw).isdigit(): raise ValueError('Conversa inválida.')
                c=CommercialConversation.objects.select_for_update().filter(pk=raw).first()
                if not c: return Response({'detail':'Conversa não encontrada.'},status=404)
                if action=='resume':
                    if c.opted_out: raise ValueError('Contato recusou mensagens; retomada automática bloqueada.')
                    if otp_excluded(c.phone, c.instance): raise ValueError('Conversa de OTP excluída permanentemente da automação comercial.')
                    if c.messages.filter(state__in=['sending','uncertain']).exists(): raise ValueError('Envio incerto: concilie na Evolution antes de retomar.')
                    c.paused=False;c.reason='';c.owner=None
                elif action=='takeover':
                    c.paused=True;c.reason='human_takeover';c.owner=request.user
                    CommercialHandoffAlert.objects.filter(conversation=c,state='pending').update(state='acknowledged', acknowledged_at=timezone.now())
                else:
                    stage=request.data.get('stage',c.stage)
                    if stage not in dict(CommercialConversation._meta.get_field('stage').choices): raise ValueError('Etapa inválida.')
                    c.stage=stage;c.notes=str(request.data.get('notes',c.notes))[:4000];c.name=str(request.data.get('name',c.name))[:120]
                if action in {'takeover', 'resume'}:
                    c.messages.filter(state='queued').update(state='held')
                c.save();CommercialAudit.objects.create(actor=request.user,conversation=c,action=action)
                return Response({'detail':'Conversa atualizada. Mensagens retidas não são reenviadas.'})
            else: raise ValueError('Ação inválida.')
        except ValueError as exc:
            return Response({'detail':str(exc)},status=400)
        except Exception:
            # Remote bodies/API keys must never cross this boundary.
            return Response({'detail':'A operação não foi confirmada. Consulte a saúde da conexão antes de repetir.'},status=502)
        CommercialAudit.objects.create(actor=request.user,action=action)
        return Response({'detail':'Configuração comercial atualizada.'})
