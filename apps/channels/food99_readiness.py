"""Evidence-based 99Food sandbox rollout checklist, without provider I/O.

This report is intentionally NOT an authorization to enable live 99Food.
Its external contract checks are permanently pending until supported by
independently verified provider documentation and sandbox observations.
"""
from django.conf import settings
from django.db.models import Count
from .models import Connection, ExternalOrder, Inbox, Outbox, Food99StagedOrder


def build_readiness(*, tenant):
    """Read-only snapshot for one tenant; no credentials, raw payloads or PII."""
    from .food99_telemetry import hml_only
    if not hml_only():
        raise ValueError('Diagnóstico disponível apenas no sandbox isolado de homologação.')
    connections = Connection.objects.filter(
        tenant=tenant, provider='99food', mode='test', enabled=False)
    orders = ExternalOrder.objects.filter(connection__in=connections,
                                          order__tenant=tenant, order__source='99food')
    inbox = Inbox.objects.filter(connection__in=connections)
    outbox = Outbox.objects.filter(external_order__in=orders)
    staged = Food99StagedOrder.objects.filter(connection__in=connections)
    def check(key, label, ok, detail):
        return {'key': key, 'label': label, 'state': 'passed' if ok else 'blocked', 'detail': detail}

    internal_checks = [
        check('isolated_sandbox', 'Sandbox isolado',
              not getattr(settings, 'CHANNELS_LIVE_ENABLED', False)
              and not getattr(settings, 'CHANNELS_NETWORK_ENABLED', False),
              'Sem habilitação genérica de rede ou canais reais.'),
        check('single_connection', 'Vínculo único de loja', connections.count() == 1,
              'Uma conexão 99Food de teste desativada vinculada ao tenant.'),
        check('signed_capture', 'Captura de webhook',
              getattr(settings, 'FOOD99_WEBHOOK_CAPTURE_ENABLED', False) is True,
              'Captura assinada depende da chave e das proteções do callback.'),
        check('observed_events', 'Webhooks observados', inbox.exists(),
              'Existência de eventos persistidos; não equivale a aceite operacional.'),
        check('observed_imports', 'Pedidos importados', orders.exists(),
              'Pedido importado para o tenant; não prova fluxo ponta a ponta atual.'),
        check('no_pending_remote_writes', 'Outbox sem comandos indefinidos',
              not outbox.filter(state__in=('sending', 'awaiting', 'uncertain', 'pending')).exists(),
              'Comandos indefinidos requerem reconciliação, nunca reenvio automático.'),
        check('no_processing_errors', 'Inbox sem erros de processamento',
              not inbox.filter(state='error').exists(),
              'Eventos intencionalmente bloqueados em quarentena não são erros.'),
    ]
    # Do not use missing observations as proof of readiness, and do not infer
    # provider status mappings from code or locally simulated data.
    external_checks = [
        {'key': 'pickup_sandbox', 'label': 'Retirada real no sandbox', 'state': 'external_pending',
         'detail': 'Pendente de cenário oficial 99Food com delivery_type=0.'},
        {'key': 'platform_delivery_sandbox', 'label': 'Entrega pela plataforma', 'state': 'external_pending',
         'detail': 'Pendente de cenário oficial com delivery_type=1 e seus eventos.'},
        {'key': 'delivery_status_contract', 'label': 'Contrato deliveryStatus', 'state': 'external_pending',
         'detail': 'Estados e campos não devem ser inventados.'},
        {'key': 'refund_contract', 'label': 'Reembolso e disputas', 'state': 'external_pending',
         'detail': 'Contrato e casos reais não homologados.'},
        {'key': 'cancellation_request_contract', 'label': 'Solicitações de cancelamento', 'state': 'external_pending',
         'detail': 'Necessária validação do fluxo iniciado pelo cliente/plataforma.'},
        {'key': 'distributed_workers', 'label': 'Concorrência multi-worker real', 'state': 'external_pending',
         'detail': 'Testes unitários não comprovam recuperação distribuída.'},
        {'key': 'live_credentials_and_contract', 'label': 'Liberação de produção', 'state': 'external_pending',
         'detail': 'Exige autorização, credenciais e contrato oficial de produção.'},
    ]
    mode_counts = dict(orders.values('delivery_by').annotate(n=Count('pk')).values_list('delivery_by', 'n'))
    status_counts = dict(orders.values('order__status').annotate(n=Count('pk')).values_list('order__status', 'n'))
    return {
        'sandbox_only': True, 'read_only': True, 'release_authorized': False,
        'internal_checks': internal_checks, 'external_checks': external_checks,
        'internal_passed': sum(c['state'] == 'passed' for c in internal_checks),
        'internal_total': len(internal_checks),
        'external_pending': len(external_checks),
        'order_modes': mode_counts, 'order_statuses': status_counts,
        'staged_review_count': staged.filter(state='review').count(),
        'unresolved_command_count': outbox.filter(state__in=('sending', 'awaiting', 'uncertain', 'pending')).count(),
        'summary': 'Auditoria local; aprovação de testes não autoriza integração em produção.',
    }
