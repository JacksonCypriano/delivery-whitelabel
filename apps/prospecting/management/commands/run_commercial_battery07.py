"""Explicit, resumable Gemini evaluation; never activates or sends WhatsApp."""
import json
import time
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from apps.billing.models import BillingSettings
from apps.prospecting.commercial import articles
from apps.prospecting.commercial_catalog import published_catalog
from apps.prospecting.commercial_models import CommercialControl
from apps.prospecting.commercial_battery import CASES, evaluate, metadata, write_reports


class Command(BaseCommand):
    help='Bateria original de 100 casos. Sem --allow-gemini apenas valida e lista cenários.'

    def add_arguments(self, parser):
        parser.add_argument('--allow-gemini',action='store_true')
        parser.add_argument('--output',default='/tmp/vdd-bateria-07')
        parser.add_argument('--limit',type=int,default=8)
        parser.add_argument('--resume',action='store_true')

    def handle(self,*args,**options):
        cases=json.loads(CASES.read_text())
        if not options['allow_gemini']:
            self.stdout.write(f'{len(cases)} cenários preservados; nenhuma chamada externa realizada.')
            return
        if not 1 <= options['limit'] <= 100: raise CommandError('Limite deve ser entre 1 e 100.')
        control=CommercialControl.objects.filter(pk=1).first()
        if (getattr(settings,'COMMERCIAL_AGENT_ENABLED',False) or not control
                or control.enabled or control.instance):
            raise CommandError('Exige agente desativado e controle sem instância. Nenhuma configuração foi alterada.')
        if not BillingSettings.objects.filter(pk=1).exists(): raise CommandError('Catálogo de cobrança não configurado.')
        publication=published_catalog(control)
        knowledge=articles()
        if not knowledge: raise CommandError('Conhecimento publicado ausente.')
        if not control.demo_url:
            self.stdout.write('Caso 094: demo_url ausente; encaminhamento humano é obrigatório, mesmo com expectativa original de resposta.')
        published_slugs = {article.slug for article in knowledge}
        for slug in ('objecao-valor', 'objecao-canais'):
            if slug not in published_slugs:
                self.stdout.write('Cobertura ausente: ' + slug + '. Revisar/publicar no fluxo comercial existente.')
        info=metadata(publication,knowledge)
        info['model']=settings.COMMERCIAL_AGENT_GEMINI_MODEL
        output=Path(options['output'])
        checkpoint=output/'checkpoint.json'
        rows=[]
        if checkpoint.exists():
            if not options['resume']: raise CommandError('Já existe relatório. Use --resume ou outro diretório.')
            saved=json.loads(checkpoint.read_text())
            if saved['metadata'] != info: raise CommandError('Modelo, catálogo ou artigos mudaram; use novo diretório.')
            rows=saved['rows']
        by_id={row['id']:row for row in rows}
        count=0
        for case in cases:
            old=by_id.get(case['id'])
            if old and old['outcome'] not in {'deferred','api_error','execution_error'}: continue
            if old and old.get('retry_at',0)>time.time():
                self.stdout.write(f"Aguardando cota até {old['retry_at']:.0f} (Unix UTC). Retome depois.")
                break
            row=evaluate(case,publication,knowledge)
            by_id[case['id']]=row
            rows=sorted(by_id.values(),key=lambda r:int(r['id']))
            write_reports(output,rows,info)
            self.stdout.write(f"{case['id']:>3} {row['outcome']}")
            count+=1
            if row['outcome'] in {'deferred','api_error','execution_error'} or count>=options['limit']: break
        self.stdout.write(f'{len(rows)}/100 casos registrados. Relatórios: {output}. Use --resume para continuar.')
