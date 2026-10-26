import hashlib
from copy import copy
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.contrib.admin.options import IncorrectLookupParameters
from django.db import transaction, models
from django.db.models.functions import Cast
from django.http import QueryDict
from django.utils import timezone
from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError as APIValidationError,
)
from apps.core.models import AdminSelection, AdminSelectionItem
from .pagination import paged_admin


def filtered(admin, raw, query):
    raw = copy(raw)
    raw.GET = QueryDict(query, mutable=True)
    for key in ("p", "all", "page_size"):
        raw.GET.pop(key, None)
    try:
        return paged_admin(admin, raw).get_changelist_instance(raw).queryset
    except (ValueError, ValidationError, IncorrectLookupParameters) as exc:
        raise APIValidationError("Filtro inválido.") from exc


def pk_strings(qs):
    return (
        qs.order_by("pk")
        .annotate(selection_pk=Cast("pk", models.CharField()))
        .values_list("selection_pk", flat=True)
        .iterator(chunk_size=1000)
    )


def digest(qs):
    checksum = hashlib.sha256()
    count = 0
    for pk in pk_strings(qs):
        checksum.update((pk + "\n").encode())
        count += 1
    return count, checksum.hexdigest()


@transaction.atomic
def create_selection(admin, raw, resource, scope):
    qs = filtered(admin, raw, raw.GET.urlencode())
    snapshot = AdminSelection.objects.create(
        actor=raw.user,
        tenant=getattr(raw, "tenant", None),
        scope=scope,
        resource=resource,
        query=raw.GET.urlencode(),
        count=0,
        fingerprint="",
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    batch = []
    checksum = hashlib.sha256()
    count = 0
    for pk in pk_strings(qs):
        checksum.update((pk + "\n").encode())
        count += 1
        batch.append(AdminSelectionItem(selection=snapshot, object_pk=pk))
        if len(batch) == 1000:
            AdminSelectionItem.objects.bulk_create(batch)
            batch = []
    if batch:
        AdminSelectionItem.objects.bulk_create(batch)
    snapshot.count = count
    snapshot.fingerprint = checksum.hexdigest()
    snapshot.save(update_fields=["count", "fingerprint"])
    return snapshot


def selected_queryset(admin, raw, resource, scope, token):
    try:
        snapshot = AdminSelection.objects.select_for_update().get(
            pk=token,
            actor=raw.user,
            tenant=getattr(raw, "tenant", None),
            resource=resource,
            scope=scope,
        )
    except (AdminSelection.DoesNotExist, ValueError, ValidationError):
        raise PermissionDenied("Seleção inválida.")
    if snapshot.expires_at <= timezone.now() or snapshot.consumed_at:
        raise APIValidationError(
            "Seleção expirada ou já executada. Selecione novamente."
        )
    qs = filtered(admin, raw, snapshot.query)
    # Freeze membership using a DB subquery rather than unbounded request IDs/SQL parameters.
    frozen = (
        admin.get_queryset(raw)
        .alias(selection_pk=Cast("pk", models.CharField()))
        .filter(selection_pk__in=snapshot.items.values("object_pk"))
    )
    list_ids = (
        admin.model.objects.filter(pk__in=frozen.values("pk"))
        .order_by("pk")
        .select_for_update()
    )
    for obj in list_ids.iterator(chunk_size=1000):
        if not admin.has_view_permission(raw, obj):
            raise PermissionDenied()
    if (
        digest(qs) != (snapshot.count, snapshot.fingerprint)
        or frozen.count() != snapshot.count
    ):
        raise APIValidationError(
            "Os resultados do filtro mudaram. Selecione e confira novamente."
        )
    return frozen, snapshot


def finalize_selection(snapshot, response=None):
    """Consume only a successfully completed global admin selection.

    Called inside the ResourceAction atomic transaction, including for custom
    Django Admin actions that return a response instead of None.
    """
    if response is not None:
        if response.status_code >= 400:
            transaction.set_rollback(True)
            return
        data = getattr(response, "data", None)
        if isinstance(data, dict) and data.get("confirmation_required"):
            return
        # An admin action may return an additional confirmation template.
        from django.template.response import SimpleTemplateResponse

        if isinstance(response, SimpleTemplateResponse):
            return
    if snapshot is not None:
        snapshot.consumed_at = timezone.now()
        snapshot.save(update_fields=["consumed_at"])
