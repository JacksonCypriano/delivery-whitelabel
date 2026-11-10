"""Reviewable copy for existing articles. Never enables or publishes anything."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.prospecting.commercial_models import CommercialArticle, CommercialControl
from apps.prospecting.commercial_copy import units
from types import SimpleNamespace

COPY = Path(__file__).resolve().parents[2] / 'fixtures' / 'commercial_copy_final.json'


class Command(BaseCommand):
    help = 'Mostra as 15 propostas. --apply cria revisões em rascunho, somente com agente pausado.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        proposed = json.loads(COPY.read_text())
        if options['apply']:
            control = CommercialControl.objects.select_for_update().filter(pk=1).first()
            if not control or control.enabled:
                raise CommandError('Pause o agente no painel antes de preparar revisões.')
        for row in proposed:
            if len(row['body']) > 1100:
                raise CommandError('Proposta excede o limite editorial: ' + row['slug'])
            units(SimpleNamespace(**row, pk=0, version=0))
            latest = CommercialArticle.objects.filter(slug=row['slug']).order_by('-version').first()
            self.stdout.write('\n' + row['slug'] + '\n' + row['body'])
            if options['apply'] and (not latest or latest.body != row['body']):
                CommercialArticle.objects.create(**row, version=latest.version + 1 if latest else 1, published=False)
        self.stdout.write('Nenhuma publicação ou ativação. Rascunhos mais recentes suspendem a versão anterior até revisão no painel.')
