"""One-shot 99Food sandbox confirmation, disabled until pilot authorization.

Separate from generic channel drain and transition endpoints. Uses durable
Outbox reservation before HTTP, never retries an uncertain provider write, and
never changes a local order status optimistically. No live-mode support.
"""
from datetime import timedelta
import requests

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .connectors import ProviderError
from .food99_auth import BASE_URL, get_shop_token
from .food99_import import preview
from .food99_orders import get_order_detail
from .food99_sandbox_promotion import _check_snapshot
from .food99_semantics import semantic_fingerprint
from .models import Connection, ExternalOrder, Food99StagedOrder, Outbox


def _guard():
    if (getattr(settings, 'SETTINGS_MODULE', '') != 'config.settings.hml'
            or not getattr(settings, 'FOOD99_SANDBOX_ENABLED', False)
            or getattr(settings, 'CHANNELS_LIVE_ENABLED', False)
            or getattr(settings, 'CHANNELS_NETWORK_ENABLED', False)
            or not getattr(settings, 'FOOD99_SANDBOX_IMPORT_TO_ORDERS', False)):
        raise ProviderError('Confirmação 99Food exige sandbox isolado e importação revisada.')


def _eligible_order(x):
    c = x.connection
    if (c.provider != '99food' or c.mode != 'test' or c.enabled
            or x.order.tenant_id != c.tenant_id or x.order.source != '99food'
            or x.order.status != 'pending'):
        raise ProviderError('Pedido não elegível para confirmação 99Food.')
    row = Food99StagedOrder.objects.filter(
        connection=c, external_id=x.external_id,
        app_shop_id='vdd-' + c.tenant.slug, state='reviewed',
    ).first()
    if row is None:
        raise ProviderError('Revisão de pedido sandbox ausente.')
    _detail, data = _check_snapshot(row)
    if data['status_code'] != 100:
        raise ProviderError('Status externo não homologado para confirmação.')
    if timezone.now() - data['created_at'] > timedelta(minutes=4):
        raise ProviderError('Pedido fora da janela para confirmação de até cinco minutos.')
    if data['created_at'] > timezone.now() + timedelta(seconds=30):
        raise ProviderError('Relógio de criação do pedido inválido.')
    return row, data


def _remote_confirm(app_shop_id, order_id):
    """POST JSON per supplied Swagger. Never return raw response or log tokens."""
    token = get_shop_token(app_shop_id)
    try:
        response = requests.post(
            BASE_URL + '/v1/order/order/confirm',
            json={'auth_token': token, 'order_id': int(order_id)},
            timeout=(3, 7), allow_redirects=False,
        )
    except requests.RequestException:
        raise ProviderError('Confirmação 99Food com resultado incerto; consulte o portal.',
                            uncertain=True) from None
    if response.status_code != 200:
        raise ProviderError('Confirmação 99Food sem sucesso HTTP; consulte o portal.',
                            uncertain=True) from None
    try:
        payload = response.json()
    except ValueError:
        raise ProviderError('Resposta de confirmação inválida; consulte o portal.',
                            uncertain=True) from None
    if not isinstance(payload, dict) or payload.get('errno') != 0 or payload.get('data') is not True:
        raise ProviderError('Confirmação 99Food não aprovada; consulte o portal.',
                            uncertain=True)


def confirm_existing(*, order_id, apply=False, confirm_remote=False):
    """Preview by default. The command is reserved and committed before POST.

    A second call will never replay a command, even after process failure.
    Unknown outcome -> Outbox.uncertain, to be checked with an official GET.
    """
    _guard()
    if type(order_id) is not int or order_id <= 0:
        raise ProviderError('ID local inválido.')
    x = (ExternalOrder.objects.select_related('connection__tenant', 'order')
         .filter(order_id=order_id, connection__provider='99food',
                 connection__mode='test').first())
    if x is None:
        raise ProviderError('Pedido 99Food de teste não encontrado.')
    # Check the irreversible one-shot reservation BEFORE checking eligibility:
    # after a signed orderConfirm the Order is no longer pending, and retrying
    # this function must return an idempotent result rather than raising.
    if Outbox.objects.filter(external_order=x, target='confirmed').exists():
        return {'order_id': order_id, 'result': 'ALREADY_REQUESTED', 'sent': False}
    _row, data = _eligible_order(x)
    if not apply:
        return {'order_id': order_id, 'result': 'PREVIEW', 'sent': False}
    if (not confirm_remote or
            getattr(settings, 'FOOD99_REMOTE_CONFIRM_ENABLED', False) is not True):
        raise ProviderError('Confirmação remota desativada ou sem autorização explícita.')

    # Freshness read BEFORE claiming the irreversible command. Never hold a
    # transaction across the external GET.
    detail = get_order_detail('vdd-' + x.connection.tenant.slug, x.external_id)
    current = preview(detail, app_shop_id='vdd-' + x.connection.tenant.slug,
                      shop_id=x.connection.merchant_id, order_id=x.external_id)
    if (semantic_fingerprint(current) != semantic_fingerprint(data)
            or current['status_code'] != 100
            or any(detail.get(k) not in (None, 0) for k in
                   ('cancel_time', 'complete_time', 'shop_confirm_time'))
            or timezone.now() - current['created_at'] > timedelta(minutes=4)):
        raise ProviderError('Pedido mudou ou expirou antes da confirmação remota.')

    with transaction.atomic():
        c = Connection.objects.select_for_update().get(pk=x.connection_id)
        locked = (ExternalOrder.objects.select_for_update()
                  .select_related('connection__tenant', 'order').get(pk=x.pk))
        _row, latest = _eligible_order(locked)
        if c.enabled or semantic_fingerprint(latest) != semantic_fingerprint(current):
            raise ProviderError('Pedido mudou durante a preparação do comando.')
        if Outbox.objects.filter(external_order=locked, target='confirmed').exists():
            return {'order_id': order_id, 'result': 'ALREADY_REQUESTED', 'sent': False}
        cmd = Outbox.objects.create(
            external_order=locked, target='confirmed', from_status='pending',
            payload={'food99_sandbox_one_shot': True}, state='sending',
            attempts=1, sent_at=timezone.now(),
        )
    # A crash after reservation leaves state='sending', intentionally never
    # picked up by the generic worker because connection.enabled remains False.
    try:
        _remote_confirm('vdd-' + c.tenant.slug, x.external_id)
    except ProviderError:
        Outbox.objects.filter(pk=cmd.pk, state='sending').update(
            state='uncertain', error='Resultado remoto incerto; conferência manual obrigatória.')
        return {'order_id': order_id, 'result': 'UNCERTAIN', 'sent': True}
    Outbox.objects.filter(pk=cmd.pk, state='sending').update(
        state='awaiting', error='')
    return {'order_id': order_id, 'result': 'AWAITING_WEBHOOK', 'sent': True}
