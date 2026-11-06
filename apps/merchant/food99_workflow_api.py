"""Tenant-scoped read/review/refresh operations for 99Food quarantine.

All mutating endpoints change *only* Food99StagedOrder and its revisions. No
Order/KDS/Outbox, remote accept, cancel, dispatch or webhook operation.
"""
from django.db.models import Count
from django.conf import settings
from django.core.cache import cache
from rest_framework.response import Response
from apps.merchant.api import MerchantAPI
from apps.channels.models import Food99StagedOrder, Food99StagedRevision
from apps.channels.connectors import ProviderError
from apps.channels.food99_review_workflow import acknowledge_review, refresh_staged_order, status_policy
from apps.channels.food99_review_compare import compare_revisions


def _lookup(tenant, pk):
    return (Food99StagedOrder.objects.select_related('connection')
            .filter(pk=pk, connection__tenant=tenant,
                    connection__provider='99food', connection__mode='test').first())


class Food99ReviewSummary(MerchantAPI):
    def get(self, request):
        queryset = Food99StagedOrder.objects.filter(
            connection__tenant=request.tenant,
            connection__provider='99food', connection__mode='test')
        counts = {name: 0 for name in ('review', 'changed', 'reviewed')}
        for group in queryset.values('state').annotate(total=Count('pk')):
            counts[group['state']] = group['total']
        return Response({
            'total': sum(counts.values()), 'by_state': counts,
            'operational_enabled': False, 'status_contract_confirmed': False,
            'webhook_contract_confirmed': False, 'currency_confirmed': False,
            'message': 'Revisão sandbox não libera pedidos para o KDS.',
        })


class Food99ReviewAcknowledge(MerchantAPI):
    def get(self, request, pk):
        row = _lookup(request.tenant, pk)
        if row is None:
            return Response({'detail': 'Pedido não encontrado.'}, status=404)
        return Response({'fingerprint': row.latest_fingerprint or row.fingerprint,
                         'state': row.state,
                         'status_policy': status_policy(row.last_seen_status),
                         'operational_enabled': False})

    def post(self, request, pk):
        if not getattr(settings, 'FOOD99_SANDBOX_ENABLED', False):
            return Response({'detail': 'Sandbox 99Food desabilitado.'}, status=403)
        try:
            row, result = acknowledge_review(
                tenant=request.tenant, pk=pk,
                fingerprint=request.data.get('fingerprint'))
        except ProviderError as exc:
            return Response({'detail': str(exc)}, status=409)
        return Response({'result': result, 'state': row.state,
                         'operational_enabled': False})


class Food99ReviewRefresh(MerchantAPI):
    def post(self, request, pk):
        if not getattr(settings, 'FOOD99_SANDBOX_ENABLED', False):
            return Response({'detail': 'Sandbox 99Food desabilitado.'}, status=403)
        row = _lookup(request.tenant, pk)
        if row is None:
            return Response({'detail': 'Pedido não encontrado.'}, status=404)
        if row.connection.enabled:
            return Response({'detail': 'Conexão operacional não permitida.'}, status=409)
        # Short shared-cache throttle against accidental repeated remote reads.
        cache_key = f'food99-review-refresh:{row.connection_id}:{row.pk}'
        if not cache.add(cache_key, 'busy', timeout=40):
            return Response({'detail': 'Atualização recente. Tente novamente em instantes.'}, status=429)
        try:
            refreshed, result = refresh_staged_order(tenant=request.tenant, pk=pk)
        except ProviderError:
            # No provider credentials, request URL or PII in merchant error messages.
            cache.delete(cache_key)
            return Response({'detail': 'Não foi possível atualizar o pedido de teste.'}, status=503)
        except Exception:
            cache.delete(cache_key)
            raise
        return Response({'result': result, 'status_code': refreshed.last_seen_status,
                         'state': refreshed.state, 'operational_enabled': False})


class Food99ReviewCompare(MerchantAPI):
    def get(self, request, pk):
        row = _lookup(request.tenant, pk)
        if row is None:
            return Response({'detail': 'Pedido não encontrado.'}, status=404)
        try:
            a = int(request.query_params.get('from', ''))
            b = int(request.query_params.get('to', ''))
        except (ValueError, TypeError):
            return Response({'detail': 'Versões inválidas.'}, status=400)
        if a < 1 or b <= a:
            return Response({'detail': 'Selecione duas versões em ordem crescente.'}, status=400)
        found = {revision.version: revision for revision in Food99StagedRevision.objects.filter(
            staged_order=row, version__in=[a, b])}
        if len(found) != 2:
            return Response({'detail': 'Versões não encontradas.'}, status=404)
        try:
            diff = compare_revisions(row, found[a], found[b])
        except ProviderError:
            return Response({'detail': 'Não foi possível comparar estas versões.'}, status=422)
        diff['status_policy'] = status_policy(row.last_seen_status)
        return Response(diff)
