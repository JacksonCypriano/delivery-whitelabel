"""Tenant-scoped, read-only operations overview for the isolated 99Food sandbox.

No provider calls, PII, decrypted snapshots, mutations or automatic replay.
"""
from datetime import timedelta
from django.conf import settings
from django.db.models import Count
from django.utils import timezone
from .models import Connection, ExternalOrder, Inbox, Outbox, Food99StagedOrder

TERMINAL = ('confirmed', 'failed', 'cancelled')


def hml_only():
    return (getattr(settings, 'SETTINGS_MODULE', '') == 'config.settings.hml'
            and bool(getattr(settings, 'FOOD99_SANDBOX_ENABLED', False))
            and not bool(getattr(settings, 'CHANNELS_LIVE_ENABLED', False))
            and not bool(getattr(settings, 'CHANNELS_NETWORK_ENABLED', False)))


def build_snapshot(*, tenant, limit=50, now=None):
    """Return a bounded operational report; no cross-tenant identifiers are exposed."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Limit must be between 1 and 100')
    now = now or timezone.now()
    connections = Connection.objects.filter(tenant=tenant, provider='99food', mode='test', enabled=False)
    events = Inbox.objects.filter(connection__in=connections)
    commands = Outbox.objects.filter(external_order__connection__in=connections,
                                     external_order__order__tenant=tenant,
                                     external_order__order__source='99food')
    staged = Food99StagedOrder.objects.filter(connection__in=connections)
    external = ExternalOrder.objects.filter(connection__in=connections,
                                           order__tenant=tenant, order__source='99food')
    def counts(qs):
        return {r['state']: r['n'] for r in qs.values('state').annotate(n=Count('pk'))}
    events_by_state = counts(events)
    commands_by_state = counts(commands)
    staged_by_state = counts(staged)
    alerts = []
    def add(code, severity, title, detail, action, *, order_id=None, external_id=None, age_seconds=None):
        if len(alerts) >= limit:
            return
        alerts.append({'code': code, 'severity': severity, 'title': title,
                       'detail': detail, 'action': action,
                       'order_id': order_id, 'external_id': external_id,
                       'age_seconds': age_seconds, 'provider': '99food'})
    for cmd in commands.select_related('external_order').filter(
            state__in=('sending', 'awaiting', 'uncertain', 'error', 'failed')
            ).order_by('created_at', 'pk')[:limit * 3]:
        timestamp = cmd.sent_at or cmd.created_at
        age = max(0, int((now - timestamp).total_seconds()))
        if cmd.state == 'sending' and age >= 120:
            add('REMOTE_OUTCOME_UNKNOWN', 'critical', 'Envio interrompido',
                'Comando permanece em sending após o prazo de segurança.',
                'Consultar estado oficial e Inbox antes de qualquer ação; não reenviar POST.',
                order_id=cmd.external_order.order_id, external_id=cmd.external_order.external_id, age_seconds=age)
        elif cmd.state == 'uncertain':
            add('REMOTE_OUTCOME_UNKNOWN', 'critical', 'Resultado remoto incerto',
                'Não há comprovação do resultado do comando.',
                'Conferir portal 99Food, webhook e estado remoto; nunca reenviar automaticamente.',
                order_id=cmd.external_order.order_id, external_id=cmd.external_order.external_id, age_seconds=age)
        elif cmd.state == 'awaiting' and cmd.target == 'delivered':
            add('DELIVERY_CONFIRMATION_PENDING', 'warning', 'Entrega 99Food ainda não concluída',
                'A solicitação de entrega aguarda retorno oficial. Código/localizador do sandbox não foi validado.',
                'Verifique o pedido e o procedimento oficial no portal 99Food. Não invente códigos, não altere o pedido manualmente nem reenvie a operação.',
                order_id=cmd.external_order.order_id, external_id=cmd.external_order.external_id, age_seconds=age)
        elif cmd.state == 'awaiting' and age >= 300:
            add('WEBHOOK_DELAYED', 'warning', 'Aguardando webhook',
                'Comando remoto aguardando confirmação oficial.',
                'Conferir Inbox e pedido no portal antes de decidir.',
                order_id=cmd.external_order.order_id, external_id=cmd.external_order.external_id, age_seconds=age)
        elif cmd.state in ('error', 'failed'):
            add('COMMAND_FAILED', 'warning', 'Falha registrada na Outbox',
                'Um comando precisa de diagnóstico.',
                'Conferir histórico do comando sem repetição automática.',
                order_id=cmd.external_order.order_id, external_id=cmd.external_order.external_id, age_seconds=age)
    if len(alerts) < limit:
        for event in events.filter(state__in=('error', 'blocked')).order_by('received_at', 'pk')[:limit * 2]:
            age = max(0, int((now - event.received_at).total_seconds()))
            if (event.state == 'blocked' and isinstance(event.payload, dict)
                    and event.payload.get('food99_quarantined') is True):
                continue  # Intentional quarantine is not an operational failure.
            add('INBOX_FAILED' if event.state == 'error' else 'INBOX_REVIEW',
                'warning', 'Evento precisa de análise',
                'Evento não foi concluído no processamento.',
                'Analisar tipo e estado na Inbox; preservar eventos em quarentena.',
                external_id=event.order_id, age_seconds=age)
    if len(alerts) < limit:
        for row in staged.filter(state='review').order_by('created_at', 'pk')[:limit]:
            age = max(0, int((now - row.created_at).total_seconds()))
            if age < 300:
                continue
            add('STAGED_REVIEW', 'info', 'Pedido pendente de revisão',
                'Snapshot na quarentena ainda não foi aprovado.',
                'Conferir status, fingerprint e valores na tela de revisão.',
                external_id=row.external_id, age_seconds=age)
    from .food99_readiness import build_readiness
    readiness = build_readiness(tenant=tenant)
    from .food99_integrity_audit import inspect_integrity
    integrity = inspect_integrity(tenant=tenant, limit=limit, now=now)
    backlog = {'available': False, 'reason': 'Sincronização local não habilitada em HML.'}
    if getattr(settings, 'FOOD99_LOCAL_EVENT_SYNC_ENABLED', False) is True:
        from .food99_backlog import plan_backlog
        from .connectors import ProviderError
        try:
            backlog = {'available': True, **plan_backlog(tenant_slug=tenant.slug, limit=25)}
        except ProviderError:
            backlog = {'available': False, 'reason': 'Backlog indisponível para este sandbox.'}
    return {
        'backlog': backlog,
        'integrity': integrity,
        'readiness': readiness,
        'sandbox_only': True, 'read_only': True, 'generated_at': now.isoformat(),
        'connection_count': connections.count(), 'imported_count': external.count(),
        'inbox': {'total': events.count(), 'states': events_by_state},
        'outbox': {'total': commands.count(), 'states': commands_by_state},
        'staging': {'total': staged.count(), 'states': staged_by_state},
        'alerts': alerts, 'alerts_limit': limit,
        'alert_limit_reached': len(alerts) == limit,
        'pilot_enabled': bool(getattr(settings, 'FOOD99_AUTO_PILOT_ENABLED', False)),
        'remote_confirm_enabled': bool(getattr(settings, 'FOOD99_REMOTE_CONFIRM_ENABLED', False)),
        'message': 'Diagnóstico local: não prova entrega, confirmação ou aceite remoto.',
    }
