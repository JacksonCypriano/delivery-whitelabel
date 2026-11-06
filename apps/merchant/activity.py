from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Q, CharField
from django.db.models.functions import Cast
from .schema import value


def recent_activity(request, resources, resolve, scope):
    raw = request._request
    accessible = Q(pk__in=[])
    links = {}
    for key in resources:
        admin = resolve(key)
        if not admin.has_module_permission(raw) or not admin.has_view_permission(raw):
            continue
        ct = ContentType.objects.get_for_model(admin.model)
        links[ct.pk] = (key, admin)
        ids = (
            admin.get_queryset(raw)
            .order_by()
            .annotate(text_pk=Cast("pk", CharField()))
            .values("text_pk")
        )
        accessible |= Q(content_type_id=ct.pk, object_id__in=ids)
    if scope == "merchant":
        accessible = (accessible & Q(react_scope__isnull=True)) | Q(
            react_scope__tenant_id=request.tenant.pk, content_type_id__in=links
        )
    else:
        accessible = (
            accessible & Q(react_scope__isnull=True, user__is_superuser=True)
        ) | Q(
            react_scope__tenant__isnull=True,
            react_scope__isnull=False,
            content_type_id__in=links,
        )
    qs = (
        LogEntry.objects.filter(accessible)
        .select_related("user", "content_type")
        .order_by("-action_time", "-pk")
    )
    page = Paginator(qs, 20).get_page(request.query_params.get("page"))
    rows = []
    for entry in page:
        link = None
        pair = links.get(entry.content_type_id)
        if pair and not entry.is_deletion():
            key, admin = pair
            obj = admin.get_queryset(raw).filter(pk=entry.object_id).first()
            if obj and admin.has_view_permission(raw, obj):
                link = f"/painel/{key}/{obj.pk}"
        rows.append(
            {
                "id": entry.pk,
                "date": value(entry.action_time),
                "user": str(entry.user),
                "resource": str(entry.content_type),
                "object": entry.object_repr,
                "type": entry.get_action_flag_display(),
                "action": entry.get_change_message(),
                "url": link,
            }
        )
    return {
        "rows": rows,
        "page": page.number,
        "pages": page.paginator.num_pages,
        "count": page.paginator.count,
    }
