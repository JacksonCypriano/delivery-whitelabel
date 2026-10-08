"""KDS uses the same orders, transition service, audit and realtime channel."""
from django.db import transaction
from rest_framework.response import Response
from apps.orders.models import OrderStatusEvent, OrderNotificationSettings
from apps.orders.operations import transition_order, OrderOperationError
from apps.orders.realtime import publish_order_event
from .api import MerchantAPI
from .orders import _base_queryset, _order_card, _settings_json

KITCHEN_STATES = ('confirmed', 'preparing', 'ready', 'ready_for_pickup')


class Kitchen(MerchantAPI):
    def get(self, request):
        settings, _ = OrderNotificationSettings.objects.get_or_create(tenant=request.tenant)
        rows = _base_queryset(request.tenant).filter(status__in=KITCHEN_STATES).order_by('-kitchen_priority', 'created_at', 'pk')
        cards = []
        for row in rows:
            card = _order_card(row, settings=settings)
            card['allowed_transitions'] = [a for a in card['allowed_transitions'] if a['value'] in ('preparing', 'ready', 'ready_for_pickup')]
            cards.append(card)
        return Response({'orders': cards, 'notification_settings': _settings_json(settings)})


class KitchenAction(MerchantAPI):
    @transaction.atomic
    def post(self, request, pk):
        order = _base_queryset(request.tenant).select_for_update(of=("self",)).filter(pk=pk).first()
        if order is None:
            return Response({'detail': 'Pedido não encontrado.'}, status=404)
        if order.status not in KITCHEN_STATES:
            return Response({'detail': 'Este pedido não está na cozinha.'}, status=400)
        if 'priority' in request.data:
            priority = request.data['priority']
            if not isinstance(priority, bool):
                return Response({'detail': 'Prioridade deve ser verdadeira ou falsa.'}, status=400)
            if order.kitchen_priority != priority:
                order.kitchen_priority = priority
                order.save(update_fields=['kitchen_priority'])
                OrderStatusEvent.objects.create(tenant=request.tenant, order=order, actor=request.user,
                    from_status=order.status, to_status=order.status, source='panel',
                    note='Prioridade da cozinha atualizada.', metadata={'origin': 'kds', 'priority': priority})
                transaction.on_commit(lambda: publish_order_event(order.pk, request.tenant.pk))
            return Response({'detail': 'Prioridade atualizada.'})
        target = request.data.get('status')
        if target not in ('preparing', 'ready', 'ready_for_pickup'):
            return Response({'detail': 'Ação não permitida na cozinha.'}, status=400)
        try:
            order, event = transition_order(order_id=pk, tenant=request.tenant, actor=request.user,
                target_status=target, note='Alterado no KDS.', message=request.data.get('message'),
                complement=request.data.get('complement', ''), send_notification=request.data.get('send_notification'),
                prep_minutes=request.data.get('prep_minutes'), fulfillment_minutes=request.data.get('fulfillment_minutes'))
        except OrderOperationError as exc:
            return Response({'detail': str(exc)}, status=400)
        if event:
            event.metadata = {**event.metadata, 'origin': 'kds'}
            event.save(update_fields=['metadata'])
        return Response({'detail': 'Cozinha atualizada.', 'order': _order_card(order)})
