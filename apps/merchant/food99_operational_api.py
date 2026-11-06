"""Merchant endpoints for sandbox-only 99Food preflight and bounded reads."""
from django.conf import settings
from django.db.models import Count
from rest_framework.response import Response

from apps.channels.connectors import ProviderError
from apps.channels.models import Connection, Food99StagedOrder
from apps.channels.food99_operational_preview import preview_staged, readiness
from apps.channels.food99_integrity import audit_summary
from apps.channels.food99_sandbox_batch import stage_by_id, refresh_batch
from .api import MerchantAPI


def _review_row(tenant, pk):
    return Food99StagedOrder.objects.select_related('connection').filter(
        pk=pk, connection__tenant=tenant,
        connection__provider='99food', connection__mode='test',
    ).first()


class Food99OperationalReadiness(MerchantAPI):
    def get(self, request):
        connections = Connection.objects.filter(
            tenant=request.tenant, provider='99food', mode='test',
        ).exclude(merchant_id__startswith='request-').order_by('pk')
        conn = connections.first()
        staged = Food99StagedOrder.objects.filter(
            connection__tenant=request.tenant,
            connection__provider='99food', connection__mode='test',
        )
        stats = staged.aggregate(total=Count('pk'))
        codes = staged.values_list('last_seen_status', flat=True).distinct()[:100]
        return Response(readiness(
            sandbox_enabled=getattr(settings, 'FOOD99_SANDBOX_ENABLED', False),
            connection=conn,
            staged_count=stats['total'],
            reviewed_count=staged.filter(state='reviewed').count(),
            statuses=codes,
        ))


class Food99OperationalPreview(MerchantAPI):
    def get(self, request, pk):
        row = _review_row(request.tenant, pk)
        if row is None:
            return Response({'detail': 'Pedido não encontrado.'}, status=404)
        try:
            return Response(preview_staged(row))
        except ProviderError:
            return Response({'detail': 'Não foi possível montar a prévia.'}, status=422)


class Food99SandboxStage(MerchantAPI):
    def post(self, request):
        raw_id = request.data.get('order_id')
        if not isinstance(raw_id, str):
            return Response({'detail': 'Informe o ID numérico do pedido.'}, status=400)
        try:
            row, outcome = stage_by_id(tenant=request.tenant, order_id=raw_id)
        except ProviderError:
            # Do not leak identifiers or remote provider messages.
            return Response({'detail': 'Não foi possível consultar ou registrar o pedido sandbox.'}, status=409)
        return Response({
            'id': row.pk, 'external_id': row.external_id,
            'result': outcome, 'operational_enabled': False,
            'kds_visible': False,
        })


class Food99SandboxBatchRefresh(MerchantAPI):
    def post(self, request):
        try:
            results = refresh_batch(tenant=request.tenant, ids=request.data.get('ids'))
        except ProviderError:
            return Response({'detail': 'Seleção inválida ou indisponível para esta loja.'}, status=400)
        return Response({'results': results,
                         'operational_enabled': False, 'kds_visible': False})


class Food99IntegrityAudit(MerchantAPI):
    """Bounded tenant-level quarantine integrity scan with no personal data."""
    def get(self, request):
        queryset = Food99StagedOrder.objects.filter(
            connection__tenant=request.tenant,
            connection__provider='99food', connection__mode='test',
        ).select_related('connection').annotate(
            revision_count=Count('revisions')
        ).order_by('-updated_at', '-pk')
        limit = 100
        total = queryset.count()
        rows = list(queryset[:limit])
        return Response(audit_summary(rows, total=total, limit=limit))


class Food99OperationalDryRun(MerchantAPI):
    """Tenant-scoped, read-only scenario; no Order, stock, KDS or provider calls."""
    def get(self, request, pk):
        from apps.channels.food99_operational_dryrun import dry_run_staged
        row = _review_row(request.tenant, pk)
        if row is None:
            return Response({'detail': 'Pedido não encontrado.'}, status=404)
        try:
            return Response(dry_run_staged(row))
        except ProviderError:
            return Response({'detail': 'Simulação indisponível para este pedido.'}, status=422)


class Food99OperationalBatchDryRun(MerchantAPI):
    """At most five tenant-owned rows, read only and without outbound requests."""
    def post(self, request):
        from apps.channels.food99_operational_dryrun import dry_run_staged
        ids = request.data.get('ids')
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 5 or
                any(type(pk) is not int or pk < 1 for pk in ids) or
                len(ids) != len(set(ids))):
            return Response({'detail': 'Informe de 1 a 5 IDs internos distintos.'}, status=400)
        rows = Food99StagedOrder.objects.select_related('connection').filter(
            pk__in=ids, connection__tenant=request.tenant,
            connection__provider='99food', connection__mode='test',
            connection__enabled=False,
        )
        mapping = {row.pk: row for row in rows}
        if len(mapping) != len(ids):
            return Response({'detail': 'Um ou mais pedidos não foram encontrados.'}, status=404)
        results = []
        for pk in ids:
            try:
                report = dry_run_staged(mapping[pk])
                results.append({'id': pk, 'status_code': report['status_code'],
                                'items_count': report['items_count'],
                                'diagnostics': report['diagnostics'],
                                'operational_enabled': False})
            except ProviderError:
                results.append({'id': pk, 'error': 'SNAPSHOT_UNAVAILABLE',
                                'operational_enabled': False})
        return Response({'results': results, 'orders_created': 0,
                         'operational_enabled': False, 'kds_visible': False})


class Food99SimulatedImport(MerchantAPI):
    """Only explicitly permitted HML/test exercise; never acknowledges provider."""
    def post(self, request):
        from apps.channels.food99_simulated_operation import import_simulated, simulation_enabled
        if not simulation_enabled():
            return Response({'detail':'Simulação indisponível.'}, status=404)
        pk = request.data.get('staged_id')
        if type(pk) is not int or pk <= 0:
            return Response({'detail':'ID interno inválido.'}, status=400)
        try:
            order, created = import_simulated(tenant=request.tenant, staged_id=pk, actor=request.user)
        except ProviderError:
            return Response({'detail':'Revisão não disponível para simulação.'}, status=422)
        return Response({'order_id':order.pk, 'created':created,
                         'simulation':True, 'provider_synced':False,
                         'message':'Pedido de simulação criado nas telas de operação.'})


class Food99SimulationAvailability(MerchantAPI):
    def get(self, request):
        from apps.channels.food99_simulated_operation import simulation_enabled
        return Response({'available':simulation_enabled(), 'provider_synced':False,
                         'webhooks_enabled':False})


class Food99SimulatedEvent(MerchantAPI):
    """Advance a deterministic local-only synthetic event, never a provider webhook."""
    def post(self, request):
        from apps.channels.food99_simulated_operation import advance_simulated_event, simulation_enabled
        if not simulation_enabled():
            return Response({'detail':'Simulação indisponível.'}, status=404)
        pk = request.data.get('order_id')
        if type(pk) is not int or pk <= 0:
            return Response({'detail':'ID de pedido inválido.'}, status=400)
        try:
            order, advanced = advance_simulated_event(tenant=request.tenant, order_id=pk)
        except ProviderError:
            return Response({'detail':'Evento sintético não pôde ser processado.'}, status=422)
        return Response({'order_id':order.pk, 'status':order.status,
                         'advanced':advanced, 'provider_synced':False,
                         'simulated_event':True})


class Food99Telemetry(MerchantAPI):
    """Read-only diagnostics; available to tenant admins only in the isolated HML sandbox."""
    def get(self, request):
        from apps.channels.food99_telemetry import build_snapshot, hml_only
        if not hml_only():
            return Response({'detail': 'Disponível apenas em homologação.'}, status=404)
        return Response(build_snapshot(tenant=request.tenant))


class Food99BacklogPreview(MerchantAPI):
    """Read-only, cursor-paginated sandbox events for imported tenant orders."""
    def get(self, request):
        from apps.channels.food99_backlog import plan_backlog
        try:
            limit = int(request.query_params.get('limit', '25'))
            cursor = int(request.query_params.get('cursor', '0'))
            return Response(plan_backlog(tenant_slug=request.tenant.slug,
                                         limit=limit, cursor=cursor))
        except (ValueError, TypeError, ProviderError):
            return Response({'detail': 'Diagnóstico indisponível ou parâmetros inválidos.'}, status=400)
