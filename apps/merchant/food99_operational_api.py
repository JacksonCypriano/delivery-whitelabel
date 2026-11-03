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
