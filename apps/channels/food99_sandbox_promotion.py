"""Deliberate, fail-closed sandbox-only promotion of a reviewed 99Food order.

This is not automated acceptance of provider orders: production is refused,
remote writes are absent, and an operator must affirm the BRL assumption.
Only a recent, signed orderNew, never a canceled/finished or unknown-status
order, can be projected into a local Order for integration/KDS verification.
"""
import json
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.billing.secrets import decrypt_secret
from .connectors import ProviderError
from .food99_import import import_reviewed, preview
from .food99_orders import get_order_detail
from .food99_semantics import semantic_fingerprint
from .models import Food99StagedOrder, Food99StagedRevision, Inbox, ExternalOrder


def _guard():
    if (getattr(settings, 'SETTINGS_MODULE', '') != 'config.settings.hml'
            or not getattr(settings, 'FOOD99_SANDBOX_ENABLED', False)
            or getattr(settings, 'CHANNELS_LIVE_ENABLED', False)
            or getattr(settings, 'CHANNELS_NETWORK_ENABLED', False)):
        raise ProviderError('Promoção disponível somente em homologação isolada.')


def _check_snapshot(row):
    connection = row.connection
    if (connection.provider != '99food' or connection.mode != 'test'
            or connection.enabled or row.app_shop_id != 'vdd-' + connection.tenant.slug
            or row.state != 'reviewed'):
        raise ProviderError('Pedido não revisado ou conexão não autorizada.')
    snapshot = row.latest_encrypted_snapshot or row.encrypted_snapshot
    try:
        detail = json.loads(decrypt_secret(snapshot))
        data = preview(detail, app_shop_id=row.app_shop_id,
                       shop_id=connection.merchant_id, order_id=row.external_id)
    except (ValueError, KeyError, TypeError, OverflowError, ProviderError):
        raise ProviderError('Snapshot 99Food inválido para promoção.') from None
    fingerprint = semantic_fingerprint(data)
    if fingerprint != (row.latest_fingerprint or row.fingerprint):
        raise ProviderError('Pedido alterado após revisão.')
    # A status=100 occurs in the official orderNew example. It is ONLY a
    # limited, explicitly reviewed sandbox admission criterion; not a provider
    # status mapping nor permission to send an acceptance/confirm API call.
    if data['status_code'] != 100 or any(detail.get(k) not in (None, 0) for k in
                                          ('cancel_time', 'complete_time', 'shop_confirm_time')):
        raise ProviderError('Pedido não é uma observação nova elegível; estado 99Food não homologado.')
    # An old orderNew cannot be brought into the live operational queue: it
    # may already have been auto-cancelled by the 5-minute provider deadline.
    if not (timezone.now() - timedelta(minutes=5) <= data['created_at']
            <= timezone.now() + timedelta(seconds=30)):
        raise ProviderError('Pedido fora da janela segura de observação; reconcilie no portal.')
    candidates = Inbox.objects.filter(
        connection=connection, order_id=row.external_id, code='orderNew',
        state='blocked', payload__food99_quarantined=True,
        payload__operational_enabled=False, payload__app_shop_id=row.app_shop_id,
    ).values_list('external_id', 'payload')[:100]
    event_exists = any(
        isinstance(key, str) and key.startswith('99food-')
        and len(key) == 71 and len(key.removeprefix('99food-')) == 64
        and all(c in '0123456789abcdef' for c in key[7:])
        and payload.get('raw_sha256') == key[7:]
        for key, payload in candidates
    )
    if not event_exists:
        raise ProviderError('Falta webhook orderNew assinado e armazenado para esta loja.')
    # Keep a revision corresponding to the fingerprint that was reviewed.
    if not Food99StagedRevision.objects.filter(
        staged_order=row, fingerprint=fingerprint,
    ).exists():
        raise ProviderError('Histórico de revisão incompleto.')
    return detail, data


def promote_reviewed(*, staged_id, apply=False, confirm_brl=False):
    """Preview default; fresh provider GET is mandatory before local projection.

    This does not confirm an order externally. Never hold DB locks during HTTP.
    """
    _guard()
    try:
        staged_id = int(staged_id)
    except (TypeError, ValueError, OverflowError):
        raise ProviderError('ID de revisão inválido.') from None
    if staged_id <= 0:
        raise ProviderError('ID de revisão inválido.')
    if apply and (not confirm_brl or
                  getattr(settings, 'FOOD99_SANDBOX_IMPORT_TO_ORDERS', False) is not True):
        raise ProviderError('Importação exige opt-in de homologação e confirmação explícita de BRL.')
    row = Food99StagedOrder.objects.select_related('connection__tenant').filter(pk=staged_id).first()
    if row is None:
        raise ProviderError('Pedido em quarentena não encontrado.')
    _snapshot, data = _check_snapshot(row)
    existing = ExternalOrder.objects.filter(connection=row.connection,
                                             external_id=row.external_id).first()
    if existing is not None:
        if existing.order.tenant_id != row.connection.tenant_id:
            raise ProviderError('Importação existente pertence a outro tenant.')
        return {'staged_id': row.pk, 'eligible': True, 'imported': False,
                'existing': True, 'order_id': existing.order_id,
                'status_code': data['status_code']}
    if not apply:
        return {'staged_id': row.pk, 'eligible': True, 'imported': False,
                'existing': False, 'status_code': data['status_code']}

    # Mandatory freshness check. The order could have been canceled after
    # review; a stored snapshot is insufficient to put it into KDS.
    fresh = get_order_detail(row.app_shop_id, row.external_id)
    fresh_data = preview(fresh, app_shop_id=row.app_shop_id,
                         shop_id=row.connection.merchant_id, order_id=row.external_id)
    if (fresh_data['status_code'] != 100
            or any(fresh.get(k) not in (None, 0) for k in ('cancel_time', 'complete_time', 'shop_confirm_time'))
            or semantic_fingerprint(fresh_data) != semantic_fingerprint(data)):
        raise ProviderError('99Food retornou pedido alterado ou não elegível; reconcilie antes de importar.')
    if not (timezone.now() - timedelta(minutes=5) <= fresh_data['created_at']
            <= timezone.now() + timedelta(seconds=30)):
        raise ProviderError('Pedido expirou durante a validação.')

    # Revalidate everything while holding row lock. Only local DB operations
    # happen within this transaction; import_reviewed handles DB uniqueness.
    with transaction.atomic():
        locked = (Food99StagedOrder.objects.select_for_update()
                  .select_related('connection__tenant').get(pk=staged_id))
        _current_snapshot, current_data = _check_snapshot(locked)
        if (locked.connection_id != row.connection_id
                or locked.external_id != row.external_id
                or locked.app_shop_id != row.app_shop_id
                or semantic_fingerprint(current_data) != semantic_fingerprint(fresh_data)):
            raise ProviderError('Revisão mudou durante a consulta oficial.')
        pk, created = import_reviewed(
            fresh, tenant_id=locked.connection.tenant_id, app_shop_id=locked.app_shop_id,
            shop_id=locked.connection.merchant_id, order_id=locked.external_id,
            currency='BRL', status_override='pending')
        return {'staged_id': locked.pk, 'eligible': True, 'imported': created,
                'existing': not created, 'order_id': pk,
                'status_code': fresh_data['status_code']}
