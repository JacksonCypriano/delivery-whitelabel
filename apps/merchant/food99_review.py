"""Read-only, tenant-scoped 99Food sandbox review API.

Never decrypts snapshots, reveals PII, creates operational Orders or triggers provider calls.
"""
from rest_framework.response import Response
from apps.billing.secrets import decrypt_secret
from apps.channels.food99_import import preview
from apps.channels.connectors import ProviderError
import json
from apps.channels.models import Food99StagedOrder, Food99StagedRevision
from .api import MerchantAPI


def _order_public(row):
    return {
        "id": row.pk,
        "external_id": row.external_id,
        "state": row.state,
        "status_code": row.last_seen_status,
        "item_count": row.item_count,
        "amount_minor": row.amount_minor,
        "change_count": row.change_count,
        "revision_count": row.revision_count,
        "updated_at": row.updated_at.isoformat(),
        "app_shop_id": row.app_shop_id,
        "merchant_id": row.connection.merchant_id,
    }


class Food99ReviewList(MerchantAPI):
    """List only sandbox quarantine rows for the authenticated merchant's tenant."""

    def get(self, request):
        try:
            page = int(request.query_params.get("page", "1"))
        except (TypeError, ValueError):
            return Response({"detail": "Página inválida."}, status=400)
        if page < 1 or page > 100000:
            return Response({"detail": "Página inválida."}, status=400)
        from django.db.models import Count
        queryset = Food99StagedOrder.objects.filter(
            connection__tenant=request.tenant,
            connection__provider="99food",
            connection__mode="test",
        ).select_related("connection").annotate(
            revision_count=Count("revisions")
        ).order_by("-updated_at", "-pk")
        total = queryset.count()
        page_size = 15
        rows = queryset[(page - 1) * page_size:page * page_size]
        return Response({
            "results": [_order_public(row) for row in rows],
            "page": page, "page_size": page_size, "total": total,
            "pages": max(1, (total + page_size - 1) // page_size),
            "operational_enabled": False,
            "message": "Pedidos em revisão não são enviados ao KDS.",
        })


class Food99ReviewDetail(MerchantAPI):
    """Revision metadata only; no snapshot, token or customer data."""

    def get(self, request, pk):
        from django.db.models import Count
        row = Food99StagedOrder.objects.filter(
            pk=pk,
            connection__tenant=request.tenant,
            connection__provider="99food",
            connection__mode="test",
        ).select_related("connection").annotate(
            revision_count=Count("revisions")
        ).first()
        if row is None:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        revisions = Food99StagedRevision.objects.filter(
            staged_order=row,
        ).order_by("-version")[:50]
        # Expose only reviewed, allowlisted commerce fields. Never expose
        # customer name, telephone, address, raw payload or tokens.
        items = []
        financials = None
        detail_error = None
        try:
            snapshot = json.loads(decrypt_secret(row.latest_encrypted_snapshot or row.encrypted_snapshot))
            data = preview(snapshot, app_shop_id=row.app_shop_id,
                           shop_id=row.connection.merchant_id, order_id=row.external_id)
            items = [{"name": item["name"], "quantity": item["quantity"],
                      "line_total_minor": int(item["line_total"] * 100),
                      "notes": item["notes"],
                      "options": item["options"]} for item in data["items"]]
            financials = {"total_minor": int(data["total"] * 100),
                          "real_pay_minor": int(data["real_pay"] * 100),
                          "delivery_fee_minor": int(data["delivery_fee"] * 100),
                          "discount_minor": int(data["discount"] * 100),
                          "currency_confirmed": False}
        except (ProviderError, ValueError, KeyError, TypeError, OverflowError):
            detail_error = "Detalhes não disponíveis para este snapshot."
        return Response({
            "items": items, "financials": financials, "detail_error": detail_error,
            "order": _order_public(row),
            "revisions": [{
                "version": revision.version,
                "status_code": revision.status_code,
                "created_at": revision.created_at.isoformat(),
            } for revision in revisions],
            "operational_enabled": False,
        })
