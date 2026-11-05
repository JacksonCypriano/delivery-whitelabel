"""Read-only, tenant-scoped audit for a sandbox merchant-delivery order.

No provider API, customer handover codes, decryption, state changes or retries.
"""
from django.utils import timezone
from .connectors import ProviderError
from .models import ExternalOrder, Inbox, Outbox


def audit_delivery(*, tenant_slug, order_id):
    from .food99_telemetry import hml_only
    if not hml_only():
        raise ProviderError('Diagnóstico restrito à homologação isolada.')
    if not isinstance(tenant_slug, str) or not tenant_slug or len(tenant_slug) > 100:
        raise ProviderError('Tenant inválido.')
    if not isinstance(order_id, str) or not order_id.isdecimal() or len(order_id) > 32:
        raise ProviderError('Identificador externo inválido.')
    external = (ExternalOrder.objects.select_related('order', 'connection__tenant')
                .filter(external_id=order_id, connection__provider='99food',
                        connection__mode='test', connection__enabled=False,
                        connection__tenant__slug=tenant_slug,
                        order__tenant__slug=tenant_slug, order__source='99food').first())
    if external is None:
        raise ProviderError('Pedido sandbox não encontrado para esta loja.')
    commands = list(Outbox.objects.filter(external_order=external).order_by('pk')
                    .values('id', 'target', 'state', 'attempts', 'created_at', 'sent_at'))
    events = list(Inbox.objects.filter(connection=external.connection, order_id=order_id)
                  .order_by('pk').values('id', 'code', 'state', 'received_at'))
    delivery = next((row for row in reversed(commands) if row['target'] == 'delivered'), None)
    finished = any(row['code'] == 'orderFinish' and row['state'] == 'processed' for row in events)
    local_complete = external.order.status == 'delivered'
    pending = bool(delivery and delivery['state'] in ('pending', 'sending', 'awaiting', 'uncertain'))
    if local_complete and finished:
        assessment = 'FINALIZACAO_OBSERVADA_LOCALMENTE'
    elif pending:
        assessment = 'AGUARDANDO_CONFIRMACAO_OFICIAL'
    elif delivery and delivery['state'] in ('failed', 'error'):
        assessment = 'REVISAO_MANUAL_NECESSARIA'
    else:
        assessment = 'SEM_COMPROVACAO_DE_ENTREGA'
    return {
        'sandbox_only': True, 'read_only': True, 'provider_writes': 0,
        'generated_at': timezone.now().isoformat(),
        'order_id': external.order_id, 'external_id': external.external_id,
        'local_status': external.order.status, 'delivery_by': external.delivery_by,
        'assessment': assessment, 'delivery_command': delivery,
        'finish_webhook_processed': finished, 'commands': commands, 'events': events,
        'instruction': ('A confirmação oficial deve ser conferida no portal 99Food. '
                        'Não inventar código/localizador; não repetir o POST de entrega nem '
                        'marcar Order como delivered antes de evidência válida.'),
    }
