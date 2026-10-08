import io
import re
from decimal import Decimal, InvalidOperation
from django.http import HttpResponse
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.response import Response
from .api import MerchantAPI
from .orders import _base_queryset, _order_card
from apps.orders.models import Courier, DeliveryAssignment, DeliveryAudit
from apps.orders.operations import transition_order, OrderOperationError


class Logistics(MerchantAPI):
    def get(self, request):
        from .pagination import paginate, metadata
        assignments = {
            a.order_id: a
            for a in DeliveryAssignment.objects.filter(tenant=request.tenant, order__status__in=["ready", "out_for_delivery"])
            .select_related("courier")
            .defer("photo")
        }
        orders = []
        for order in (
            _base_queryset(request.tenant)
            .filter(delivery_type="delivery", status__in=["ready", "out_for_delivery"])
            .order_by("created_at")
        ):
            card = _order_card(order)
            a = assignments.get(order.pk)
            card["courier_id"] = a.courier_id if a else None
            orders.append(card)
        history = (
            DeliveryAssignment.objects.filter(
                tenant=request.tenant, completed_at__isnull=False
            )
            .select_related("courier")
            .defer("photo")
            .order_by("-completed_at", "-pk")
        )
        history = paginate(history, request)
        photo_ids = set(
            DeliveryAssignment.objects.filter(
                tenant=request.tenant, pk__in=[a.pk for a in history], photo__isnull=False
            ).values_list("pk", flat=True)
        )
        return Response(
            {
                "couriers": list(
                    Courier.objects.filter(tenant=request.tenant).values(
                        "id", "name", "phone", "active"
                    )
                ),
                "orders": orders,
                **metadata(history),
                "history": [
                    {
                        "has_photo": a.pk in photo_ids,
                        "events": list(
                            a.events.order_by("created_at").values(
                                "action", "courier_name", "created_at"
                            )
                        ),
                        "id": a.pk,
                        "order_id": a.order_id,
                        "courier": a.courier.name,
                        "recipient": a.recipient,
                        "completed_at": a.completed_at,
                        "latitude": a.latitude,
                        "longitude": a.longitude,
                        "photo_url": f"/api/merchant/logistics/{a.pk}/photo/",
                    }
                    for a in history
                ],
                "integrations": [
                    {
                        "name": "iFood",
                        "status": "Acesso oficial e credenciais pendentes",
                    },
                    {
                        "name": "99Food",
                        "status": "Acesso oficial e credenciais pendentes",
                    },
                ],
            }
        )

    @transaction.atomic
    def post(self, request):
        d = request.data
        action = d.get("action")
        try:
            if action == "courier":
                name = str(d.get("name", "")).strip()
                phone = re.sub(r"\D", "", str(d.get("phone", "")))
                if not 1 <= len(name) <= 120 or not 10 <= len(phone) <= 13:
                    raise ValueError("Confira nome e telefone do entregador.")
                active = d.get("active", True)
                if not isinstance(active, bool):
                    raise ValueError("Ativação inválida.")
                if d.get("id"):
                    row = (
                        Courier.objects.select_for_update(of=("self",))
                        .filter(tenant=request.tenant, pk=int(d["id"]))
                        .first()
                    )
                    if not row:
                        return Response(
                            {"detail": "Entregador não encontrado."}, status=404
                        )
                    row.name = name
                    row.phone = phone
                    row.active = active
                    row.save()
                else:
                    Courier.objects.create(
                        tenant=request.tenant, name=name, phone=phone, active=active
                    )
                return Response({"detail": "Entregador salvo."})
            if action not in ("assign", "dispatch", "complete"):
                raise ValueError("Ação inválida.")
            order = (
                _base_queryset(request.tenant)
                .select_for_update(of=("self",))
                .filter(pk=int(d.get("order")))
                .first()
            )
            if not order:
                return Response({"detail": "Pedido não encontrado."}, status=404)
            if order.delivery_type != "delivery":
                raise ValueError("Retirada não usa entregador.")
            assignment = (
                DeliveryAssignment.objects.select_for_update(of=("self",))
                .filter(tenant=request.tenant, order=order)
                .first()
            )
            if action == "complete" and assignment and assignment.completed_at:
                return Response({"detail": "Entrega já concluída."})
            if order.status not in ("ready", "out_for_delivery"):
                raise ValueError("Pedido precisa estar pronto ou em entrega.")
            if action == "assign":
                courier = (
                    Courier.objects.select_for_update(of=("self",))
                    .filter(
                        tenant=request.tenant, pk=int(d.get("courier")), active=True
                    )
                    .first()
                )
                if not courier:
                    raise ValueError("Entregador indisponível nesta loja.")
                if assignment and assignment.courier_id == courier.pk:
                    return Response({"detail": "Atribuição já registrada."})
                assignment, _ = DeliveryAssignment.objects.update_or_create(
                    tenant=request.tenant, order=order, defaults={"courier": courier}
                )
            else:
                if not assignment:
                    raise ValueError("Atribua um entregador primeiro.")
                if action == "dispatch":
                    if not assignment.courier.active:
                        raise ValueError("Entregador inativo.")
                    if order.status == "out_for_delivery":
                        return Response({"detail": "Pedido já saiu para entrega."})
                    transition_order(
                        order_id=order.pk,
                        tenant=request.tenant,
                        actor=request.user,
                        target_status="out_for_delivery",
                        note="Saída pela logística.",
                    )
                else:
                    if order.status != "out_for_delivery":
                        raise ValueError(
                            "Registre a saída antes de confirmar a entrega."
                        )
                    recipient = str(d.get("recipient", "")).strip()
                    if not 1 <= len(recipient) <= 80:
                        raise ValueError("Informe quem recebeu (até 80 caracteres).")
                    lat = d.get("latitude")
                    lon = d.get("longitude")
                    lat = None if lat in (None, "") else lat
                    lon = None if lon in (None, "") else lon
                    if (lat is None) != (lon is None):
                        raise ValueError("Informe latitude e longitude juntas.")
                    if lat is not None and lon is not None:
                        lat = Decimal(str(lat))
                        lon = Decimal(str(lon))
                        if (
                            not lat.is_finite()
                            or not lon.is_finite()
                            or not -90 <= lat <= 90
                            or not -180 <= lon <= 180
                        ):
                            raise ValueError("Localização inválida.")
                    photo = request.FILES.get("photo")
                    content = None
                    if photo:
                        if photo.size > 2_000_000:
                            raise ValueError("Foto deve ter no máximo 2 MB.")
                        with Image.open(photo) as img:
                            if (
                                img.format not in ("JPEG", "PNG", "WEBP")
                                or img.width * img.height > 12_000_000
                            ):
                                raise ValueError("Foto inválida.")
                            img = ImageOps.exif_transpose(img).convert("RGB")
                            img.thumbnail((1600, 1600))
                            out = io.BytesIO()
                            img.save(out, format="JPEG", quality=80)
                            content = out.getvalue()
                    assignment.recipient = recipient
                    assignment.latitude = lat
                    assignment.longitude = lon
                    assignment.photo = content
                    assignment.completed_at = timezone.now()
                    assignment.save()
                    transition_order(
                        order_id=order.pk,
                        tenant=request.tenant,
                        actor=request.user,
                        target_status="delivered",
                        note="Entrega comprovada pela logística.",
                    )
            DeliveryAudit.objects.create(
                tenant=request.tenant,
                assignment=assignment,
                actor=request.user,
                action=action,
                courier_name=assignment.courier.name,
            )
            return Response({"detail": "Logística atualizada."})
        except (
            ValueError,
            TypeError,
            InvalidOperation,
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
            OrderOperationError,
        ) as exc:
            transaction.set_rollback(True)
            return Response({"detail": str(exc) or "Dados inválidos."}, status=400)


class DeliveryPhoto(MerchantAPI):
    def get(self, request, pk):
        row = DeliveryAssignment.objects.filter(tenant=request.tenant, pk=pk).first()
        if not row or not row.photo:
            return Response({"detail": "Foto não encontrada."}, status=404)
        response = HttpResponse(bytes(row.photo), content_type="image/jpeg")
        response["Content-Disposition"] = 'inline; filename="comprovacao.jpg"'
        response["X-Content-Type-Options"] = "nosniff"
        return response
