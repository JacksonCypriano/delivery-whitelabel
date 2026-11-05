"""Local-only cross-table integrity audit for the sandbox pilot.

Never changes data, fetches provider API, or decrypts customer information.
IDs in this report are local primary keys, scoped to the requesting tenant.
"""
from datetime import timedelta
from django.utils import timezone
from .models import Connection, ExternalOrder, Inbox, Outbox, Food99StagedOrder


def inspect_integrity(*, tenant, limit=100, now=None):
    from .food99_telemetry import hml_only
    if not hml_only():
        raise ValueError('Auditoria disponível apenas no sandbox isolado de homologação.')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Limite inválido.')
    now = now or timezone.now()
    connections = Connection.objects.filter(tenant=tenant, provider='99food', mode='test', enabled=False)
    external = ExternalOrder.objects.filter(connection__in=connections)
    commands = Outbox.objects.filter(external_order__in=external)
    events = Inbox.objects.filter(connection__in=connections)
    staged = Food99StagedOrder.objects.filter(connection__in=connections)
    issues = []
    def issue(code, level, recommendation, *, order_pk=None, command_pk=None, event_pk=None):
        if len(issues) < limit:
            issues.append({'code': code, 'severity': level, 'order_pk': order_pk,
                           'command_pk': command_pk, 'event_pk': event_pk,
                           'recommendation': recommendation})

    for x in external.select_related('order', 'connection').order_by('pk')[:limit * 4]:
        if x.order.tenant_id != tenant.pk or x.order.source != '99food':
            issue('CROSS_TENANT_OR_SOURCE', 'critical',
                  'Bloquear a operação e investigar vínculo antes de qualquer comando.')
        if x.order.status in ('cancelled', 'delivered') and x.cancellation_state:
            issue('TERMINAL_CANCELLATION_RESIDUE', 'warning',
                  'Revisar histórico dos webhooks e limpar somente após comprovação.', order_pk=x.order_id)
        if len(issues) >= limit:
            break
    for cmd in commands.select_related('external_order').order_by('pk')[:limit * 4]:
        if cmd.state == 'sending' and (cmd.sent_at or cmd.created_at) <= now - timedelta(seconds=120):
            issue('STALE_SENDING', 'critical',
                  'Consultar status oficial; recovery --apply só marca uncertain, nunca reenvia.',
                  order_pk=cmd.external_order.order_id, command_pk=cmd.pk)
        if cmd.state == 'uncertain':
            issue('UNCERTAIN_REMOTE_POST', 'critical',
                  'Conferir a 99Food e os webhooks antes de encerrar o comando.',
                  order_pk=cmd.external_order.order_id, command_pk=cmd.pk)
        if len(issues) >= limit:
            break
    for event in events.order_by('pk')[:limit * 4]:
        if event.state == 'error':
            issue('WEBHOOK_PROCESSING_ERROR', 'warning',
                  'Inspecionar erro da Inbox; não eliminar a quarentena.', event_pk=event.pk)
        if not isinstance(event.payload, dict):
            issue('INVALID_EVENT_ENVELOPE', 'critical',
                  'Envelope de evento inválido; preservar para análise.', event_pk=event.pk)
        if len(issues) >= limit:
            break
    for row in staged.order_by('pk')[:limit * 4]:
        if row.app_shop_id != 'vdd-' + tenant.slug:
            issue('STAGING_SHOP_MISMATCH', 'critical',
                  'Bloquear promoção: app_shop_id não pertence ao tenant.')
        if len(issues) >= limit:
            break
    return {'sandbox_only': True, 'read_only': True, 'generated_at': now.isoformat(),
            'issues': issues, 'issue_limit': limit, 'truncated': len(issues) == limit,
            'counts': {'connections': connections.count(), 'orders': external.count(),
                       'commands': commands.count(), 'events': events.count(), 'staged': staged.count()},
            'warning': 'Amostragem limitada por categoria; zero achados não comprova validação remota.'}
