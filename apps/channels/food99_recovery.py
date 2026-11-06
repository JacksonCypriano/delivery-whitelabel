"""Conservative crash recovery for isolated 99Food sandbox commands.

A timed-out `sending` MAY have reached the provider. Mark uncertain; never retry.
"""
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import Outbox
from .connectors import ProviderError


def recover_stale_sending(*, tenant_slug, apply=False, older_than_seconds=120, limit=100, now=None):
    if not (getattr(settings, 'SETTINGS_MODULE', '') == 'config.settings.hml'
            and getattr(settings, 'FOOD99_SANDBOX_ENABLED', False)
            and not getattr(settings, 'CHANNELS_LIVE_ENABLED', False)
            and not getattr(settings, 'CHANNELS_NETWORK_ENABLED', False)):
        raise ProviderError('Recuperação restrita ao sandbox HML isolado.')
    if not isinstance(tenant_slug, str) or not tenant_slug or len(tenant_slug) > 100:
        raise ProviderError('Tenant inválido.')
    if type(older_than_seconds) is not int or older_than_seconds < 120:
        raise ProviderError('Janela mínima de segurança: 120 segundos.')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ProviderError('Limite inválido.')
    now = now or timezone.now()
    cutoff = now - timedelta(seconds=older_than_seconds)
    query = Outbox.objects.filter(
        external_order__connection__provider='99food', external_order__connection__mode='test',
        external_order__connection__enabled=False,
        external_order__connection__tenant__slug=tenant_slug,
        external_order__order__tenant__slug=tenant_slug,
        external_order__order__source='99food',
        payload__food99_sandbox_one_shot=True, state='sending', sent_at__lte=cutoff,
    ).order_by('sent_at', 'pk')
    ids = list(query.values_list('pk', flat=True)[:limit])
    if not apply:
        return {'mode': 'preview', 'candidate_ids': ids, 'updated': 0, 'post_sent': False}
    changed = []
    with transaction.atomic():
        # Conditional update is safe even when another worker resolves the command.
        # Select by current eligibility again rather than trusting the initial scan.
        for pk in ids:
            count = query.filter(pk=pk).update(
                state='uncertain', error='Worker interrompido; resultado remoto não verificável. Não reenviar.')
            if count:
                changed.append(pk)
    return {'mode': 'applied', 'candidate_ids': ids, 'updated': len(changed),
            'updated_ids': changed, 'post_sent': False}
