"""Sandbox-only quarantine: never creates operational Order or calls external transitions."""
from django.db import transaction
from django.conf import settings
from apps.billing.secrets import encrypt_secret
from apps.channels.connectors import ProviderError
from apps.channels.models import Connection, Food99StagedOrder
from apps.channels.food99_import import preview, fingerprint_preview


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
    signature = fingerprint_preview(data)
    current = Food99StagedOrder.objects.select_for_update().filter(
        connection=conn, external_id=str(order_id)
    ).first()
    if current:
        if current.fingerprint == signature:
            return current, 'UNCHANGED'
        # Never silently replace operator-reviewed data or merge changing status with old items.
        current.state = 'changed'
        current.change_count += 1
        current.last_seen_status = data['status_code']
        current.save(update_fields=['state', 'change_count', 'last_seen_status', 'updated_at'])
        return current, 'CHANGED_REVIEW_REQUIRED'
    row = Food99StagedOrder.objects.create(
        connection=conn, external_id=str(order_id), app_shop_id=app_shop_id,
        fingerprint=signature, last_seen_status=data['status_code'],
        item_count=len(data['items']), amount_minor=int(data['total'] * 100),
        encrypted_snapshot=encrypt_secret(__import__('json').dumps(detail, ensure_ascii=False)),
        state='review',
    )
    return row, 'STAGED_REVIEW_REQUIRED'
