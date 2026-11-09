"""Manual local evaluation, optionally from a read-only approved DB snapshot."""
import hashlib
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from apps.prospecting.commercial_local_battery import (
    CASES, evaluate, snapshot, read_snapshot, write_reports,
)
from apps.prospecting.commercial_local_knowledge import VERSION


class Command(BaseCommand):
    help = '100 cenários originais, sem IA/WhatsApp. --snapshot dispensa acesso ao banco.'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)
        parser.add_argument('--snapshot', type=Path)
        parser.add_argument('--export-snapshot', type=Path)

    def handle(self, *args, **options):
        output = Path(options['output'])
        if any((output / n).exists() for n in ('checkpoint.json', 'report.csv', 'report.md')):
            raise CommandError('Use uma nova pasta de saída; relatórios anteriores são preservados.')
        if options['snapshot'] and options['export_snapshot']:
            raise CommandError('Escolha leitura do snapshot ou exportação do banco, não ambos.')
        if options['export_snapshot'] and options['export_snapshot'].exists():
            raise CommandError('O snapshot já existe; escolha outro arquivo.')
        try:
            if options['snapshot']:
                publication, knowledge, links = read_snapshot(options['snapshot'])
            else:
                # Only on explicit execution; no contact/agent writes or status calls.
                from apps.billing.models import BillingSettings
                from apps.prospecting.commercial import articles
                from apps.prospecting.commercial_catalog import published_catalog
                from apps.prospecting.commercial_models import CommercialControl
                control = CommercialControl.objects.filter(pk=1).first()
                # Prevent catalog()'s get_or_create from creating configuration.
                if not control or not BillingSettings.objects.filter(pk=1).exists():
                    raise CommandError('Catálogo/controle ainda não configurados; nada será criado.')
                publication, knowledge = published_catalog(control), articles()
                links = dict(demo=control.demo_url, signup=control.contact_url)
                if not knowledge:
                    raise CommandError('Sem artigos publicados.')
            bundle = snapshot(publication, knowledge, links)
            if options['export_snapshot']:
                path = options['export_snapshot']
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('x') as handle:
                    json.dump(bundle, handle, ensure_ascii=False, indent=2)
            cases = json.loads(CASES.read_text())
            rows = [evaluate(case, publication, knowledge, links) for case in cases]
            info = dict(composer_version=VERSION, cases_sha256=hashlib.sha256(CASES.read_bytes()).hexdigest(),
                        snapshot_sha256=bundle['sha256'], catalog_fingerprint=publication['fingerprint'])
            write_reports(output, rows, info)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise CommandError('Falha ao ler dados aprovados ou gravar relatório. Verifique snapshot e diretório.') from exc
        answers = sum(row['outcome'] == 'answer' for row in rows)
        humans = sum(row['outcome'] == 'human' for row in rows)
        compatible = sum(row['outcome_compatible'] for row in rows)
        self.stdout.write(f'{len(rows)} cenários: {answers} respostas, {humans} humanos, {compatible} compatíveis. Revisão manual pendente. {output}')
