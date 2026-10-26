from urllib.parse import urlencode
from django import forms
from django.core.paginator import Paginator
from django.db.models import Q, CharField
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response


def lookup_base(raw, obj, inline=""):
    resource = getattr(raw, "react_resource", "")
    return (
        f'resources/{resource}/{obj.pk if obj else "new"}/relationships/?'
        + urlencode({"inline": inline})
    )


def search_relationship(request, admin, obj, form_bundle):
    form, formsets, inlines = form_bundle(admin, request._request, obj)
    prefix = request.query_params.get("inline", "")
    if prefix:
        candidates = [fs.empty_form for fs in formsets if fs.prefix == prefix]
        if not candidates:
            raise PermissionDenied()
        form = candidates[0]
    field = form.fields.get(request.query_params.get("field"))
    if (
        not isinstance(field, (forms.ModelChoiceField, forms.ModelMultipleChoiceField))
        or field.widget.is_hidden
    ):
        raise PermissionDenied()
    qs = field.queryset.all()
    term = request.query_params.get("q", "").strip()[:100]
    related_admin = admin.admin_site._registry.get(qs.model)
    if term:
        if related_admin and related_admin.get_search_fields(request._request):
            qs, duplicates = related_admin.get_search_results(
                request._request, qs, term
            )
            if duplicates:
                qs = qs.distinct()
        else:
            condition = Q()
            names = [f.name for f in qs.model._meta.fields if isinstance(f, CharField)]
            for name in names:
                condition |= Q(**{name + "__icontains": term})
            qs = qs.filter(condition) if names else qs.none()
    page = Paginator(qs.order_by(qs.model._meta.pk.name).distinct(), 25).get_page(
        request.query_params.get("page")
    )
    return Response(
        {
            "results": [
                {
                    "value": str(field.prepare_value(item)),
                    "label": field.label_from_instance(item),
                }
                for item in page
            ],
            "page": page.number,
            "more": page.has_next(),
        }
    )
