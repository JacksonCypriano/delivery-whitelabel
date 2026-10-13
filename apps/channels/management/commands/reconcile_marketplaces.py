from django.core.management.base import BaseCommand
from apps.channels.tasks import poll_ifood,drain
from apps.channels.models import Outbox,Inbox

class Command(BaseCommand):
    help='Recupera eventos por polling e processa filas duráveis. Nunca repete cegamente comandos incertos.'
    def add_arguments(self,p):
        p.add_argument('--mode',choices=['test','live'],default='test')
        p.add_argument('--retry-blocked',action='store_true',help='Após corrigir a causa, retenta SOMENTE leituras/importações bloqueadas, nunca comandos enviados.')
    def handle(self,*args,**o):
        if o['retry_blocked']:
            Inbox.objects.filter(state='blocked',connection__mode=o['mode'],connection__enabled=True).update(state='pending',attempts=0,next_attempt=None)
        poll_ifood(o['mode']);drain()
        self.stdout.write(f"Eventos com erro: {Inbox.objects.filter(state='error').count()}; comandos aguardando/ incertos: {Outbox.objects.filter(state__in=['awaiting','uncertain']).count()}. Confira também o portal; não há recuperação garantida fora da retenção do provedor.")
