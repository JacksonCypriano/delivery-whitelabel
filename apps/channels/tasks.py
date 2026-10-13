from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import Connection,Inbox,Outbox,AppToken
from .connectors import IFood,ProviderError
from .services import receive,process_event,process_command

@shared_task(soft_time_limit=110,time_limit=120)
def poll_ifood(mode='test'):
    if not settings.CHANNELS_NETWORK_ENABLED or (mode=='live' and not settings.CHANNELS_LIVE_ENABLED):return
    connections={c.merchant_id:c for c in Connection.objects.filter(provider='ifood',mode=mode,enabled=True)}
    if not connections:return
    with transaction.atomic():
        AppToken.objects.get_or_create(key='ifood:'+mode)
        token=AppToken.objects.select_for_update().get(key='ifood:'+mode)
        if token.poll_after and token.poll_after>timezone.now():return
        token.poll_after=timezone.now()+timedelta(seconds=30);token.save(update_fields=['poll_after'])
    api=IFood(mode)
    merchants=list(connections)
    for start in range(0,len(merchants),100):
        batch=merchants[start:start+100]
        try:
            events=api.poll(batch);ids=set();failed=set()
            for event in events:
                if not isinstance(event,dict):continue
                conn=connections.get(str(event.get('merchantId','')))
                if not conn or conn.merchant_id not in batch:continue
                try:
                    row=receive(conn,event)
                    ids.add(row.external_id)
                except ProviderError as exc:
                    failed.add(conn.pk)
                    Connection.objects.filter(pk=conn.pk).update(status='error',last_error=str(exc))
            # Persist BEFORE acknowledgment; cap and dedupe the documented batch.
            ids=sorted(ids)
            for i in range(0,len(ids),10000):api.acknowledge(ids[i:i+10000])
            Connection.objects.filter(pk__in=[connections[m].pk for m in batch]).update(last_sync=timezone.now())
            for merchant in batch:
                c=connections[merchant]
                if c.pk not in failed and not c.events.filter(state__in=['error','blocked']).exists():
                    Connection.objects.filter(pk=c.pk,enabled=True).update(status='connected',last_error='')
        except ProviderError as exc:
            Connection.objects.filter(pk__in=[connections[m].pk for m in batch]).update(status='error',last_error=str(exc))

@shared_task(soft_time_limit=110,time_limit=120)
def drain():
    due=Q(next_attempt__isnull=True)|Q(next_attempt__lte=timezone.now())
    Inbox.objects.filter(state='processing',next_attempt__lte=timezone.now()).update(state='error',error='Worker interrompido; importação será retomada.')
    for pk in Inbox.objects.filter(state__in=['pending','error'],connection__enabled=True).filter(due).order_by('received_at').values_list('pk',flat=True)[:50]:process_event(pk)
    Outbox.objects.filter(state='sending',sent_at__lt=timezone.now()-timedelta(minutes=3)).update(state='uncertain',error='Envio interrompido; aguarde evento ou confira no portal. Não reenviado automaticamente.')
    for pk in Outbox.objects.filter(state='pending',external_order__connection__enabled=True).filter(due).order_by('created_at').values_list('pk',flat=True)[:30]:process_command(pk)
