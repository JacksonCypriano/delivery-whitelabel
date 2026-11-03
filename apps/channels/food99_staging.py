"""99Food sandbox quarantine with append-only, encrypted snapshot revisions.

Never creates operational Orders or sends remote transitions.
"""
import json

from django.conf import settings
from django.db import transaction

from apps.billing.secrets import encrypt_secret, decrypt_secret
from apps.channels.connectors import ProviderError
from apps.channels.food99_import import preview
from apps.channels.food99_semantics import semantic_fingerprint
from apps.channels.models import Connection, Food99StagedOrder, Food99StagedRevision


def classify_fingerprint(original, latest, incoming):
    """Pure classifier; latest is optional for rows created by legacy versions."""
    if incoming == (latest or original):
        return 'UNCHANGED'
    return 'CHANGED_REVIEW_REQUIRED'


def _encrypted(detail):
    return encrypt_secret(json.dumps(detail, ensure_ascii=False, default=str))


def _append_revision(order, *, fingerprint, snapshot, status_code, version):
    return Food99StagedRevision.objects.create(
        staged_order=order, version=version, fingerprint=fingerprint,
        status_code=status_code, encrypted_snapshot=snapshot,
    )


@transaction.atomic
def stage_order(detail, *, tenant, app_shop_id, shop_id, order_id):
    if not getattr(settings, 'FOOD99_SANDBOX_ENABLED', False):
        raise ProviderError('Sandbox 99Food desabilitado.')
    if app_shop_id != 'vdd-' + tenant.slug:
        raise ProviderError('AppShopID não corresponde ao tenant.')

    conn = Connection.objects.select_for_update().filter(
        provider='99food', mode='test', merchant_id=str(shop_id), tenant=tenant,
    ).first()
    if conn is None or conn.enabled:
        raise ProviderError('Conexão sandbox não vinculada ou habilitada indevidamente.')

    data = preview(detail, app_shop_id=app_shop_id, shop_id=shop_id, order_id=order_id)
    signature = semantic_fingerprint(data)
    current = Food99StagedOrder.objects.select_for_update().filter(
        connection=conn, external_id=str(order_id),
    ).first()
    if current is None:
        snapshot = _encrypted(detail)
        current = Food99StagedOrder.objects.create(
            connection=conn, external_id=str(order_id), app_shop_id=app_shop_id,
            fingerprint=signature, latest_fingerprint=signature,
            last_seen_status=data['status_code'], item_count=len(data['items']),
            amount_minor=int(data['total'] * 100), encrypted_snapshot=snapshot,
            latest_encrypted_snapshot=snapshot, state='review', change_count=0,
        )
        _append_revision(current, version=1, fingerprint=signature,
                         snapshot=snapshot, status_code=data['status_code'])
        return current, 'STAGED_REVIEW_REQUIRED'

    # Older packages created rows without latest_fingerprint/revision records.
    # Seed the original revision from the original encrypted data; no decrypt needed.
    if not current.latest_fingerprint:
        current.latest_fingerprint = current.fingerprint
        current.latest_encrypted_snapshot = current.encrypted_snapshot
        if not Food99StagedRevision.objects.filter(staged_order=current).exists():
            _append_revision(current, version=1, fingerprint=current.fingerprint,
                             snapshot=current.encrypted_snapshot,
                             status_code=current.last_seen_status)
        current.save(update_fields=['latest_fingerprint', 'latest_encrypted_snapshot', 'updated_at'])

    if classify_fingerprint(current.fingerprint, current.latest_fingerprint, signature) == 'UNCHANGED':
        return current, 'UNCHANGED'

    # Existing rows may have fingerprints produced by the former, order-sensitive
    # algorithm. Compare the *contents* before creating a revision. This also
    # protects previously stored "reviewed" acknowledgements from a false change.
    # A malformed/undecryptable historical snapshot is NOT silently treated as
    # equivalent; in that case a new observation is kept for manual review.
    try:
        prior = json.loads(decrypt_secret(
            current.latest_encrypted_snapshot or current.encrypted_snapshot
        ))
        prior_data = preview(
            prior, app_shop_id=current.app_shop_id,
            shop_id=conn.merchant_id, order_id=current.external_id,
        )
        equivalent = semantic_fingerprint(prior_data) == signature
    except (ValueError, KeyError, TypeError, OverflowError, ProviderError):
        equivalent = False
    if equivalent:
        # Upgrade the comparison watermark in place, leaving the original
        # immutable revision hashes/snapshots and change counter untouched.
        current.latest_fingerprint = signature
        current.save(update_fields=['latest_fingerprint'])
        return current, 'UNCHANGED'


    # A previously seen fingerprint can reappear (e.g. status reversal). Preserve
    # it as a new observation because it differs from the most recent revision.
    previous = Food99StagedRevision.objects.filter(staged_order=current).order_by('-version').first()
    next_version = previous.version + 1 if previous else 1
    snapshot = _encrypted(detail)
    _append_revision(current, version=next_version, fingerprint=signature,
                     snapshot=snapshot, status_code=data['status_code'])
    current.latest_fingerprint = signature
    current.latest_encrypted_snapshot = snapshot
    current.last_seen_status = data['status_code']
    current.item_count = len(data['items'])
    current.amount_minor = int(data['total'] * 100)
    current.change_count += 1
    current.state = 'changed'
    current.save(update_fields=[
        'latest_fingerprint', 'latest_encrypted_snapshot', 'last_seen_status',
        'item_count', 'amount_minor', 'change_count', 'state', 'updated_at',
    ])
    return current, 'CHANGED_REVIEW_REQUIRED'
