"""Summarize real 99Food readiness in HML, without ever enabling it."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from apps.channels.food99_integrity import audit_summary
from apps.channels.models import Connection, Food99StagedOrder
from apps.channels.food99_operational_preview import readiness
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = 'Audita a prontidão 99Food sem consultar segredos ou modificar pedidos.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-slug', required=True)

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options['tenant_slug']).first()
        if tenant is None:
            raise CommandError('Loja não encontrada.')
        conn = Connection.objects.filter(
            tenant=tenant, provider='99food', mode='test',
        ).exclude(merchant_id__startswith='request-').first()
        qs = Food99StagedOrder.objects.filter(
            connection__tenant=tenant, connection__provider='99food',
            connection__mode='test',
        )
        report = readiness(
            sandbox_enabled=getattr(settings, 'FOOD99_SANDBOX_ENABLED', False),
            connection=conn,
            staged_count=qs.count(),
            reviewed_count=qs.filter(state='reviewed').count(),
            statuses=qs.values_list('last_seen_status', flat=True).distinct()[:100],
        )
        self.stdout.write('99Food: prontidão operacional = BLOQUEADA')
        self.stdout.write(f"Sandbox vinculado: {report['sandbox_linked']}")
        self.stdout.write(f"Pedidos armazenados: {report['staged_count']} | revisados: {report['reviewed_count']}")
        for blocker in report['blockers']:
            self.stdout.write(f"PENDENTE: {blocker['code']} - {blocker['detail']}")
        integrity_qs = qs.select_related('connection').annotate(
            revision_count=Count('revisions')
        ).order_by('-updated_at', '-pk')
        report_integrity = audit_summary(
            list(integrity_qs[:100]), total=qs.count(), limit=100,
        )
        self.stdout.write(
            f"Auditoria estrutural: {report_integrity['scanned']} inspecionados; "
            f"{report_integrity['affected_scanned']} com problemas."
        )
        for finding in report_integrity['findings']:
            self.stdout.write(f"REVISAO #{finding['id']}: {', '.join(finding['issues'])}")
        self.stdout.write('Nenhum pedido operacional criado e nenhuma transição externa executada.')
