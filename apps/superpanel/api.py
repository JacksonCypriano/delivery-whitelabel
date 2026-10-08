"""Session/CSRF-protected SuperAdmin API reusing existing Django Admin policies."""

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.admin.utils import label_for_field
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.http import Http404
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from django.shortcuts import get_object_or_404
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, NotAuthenticated, NotFound
from rest_framework.permissions import BasePermission, AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.tenants.admin_site import SuperAdminAuthenticationForm
from apps.tenants.domains import is_platform_host
from .registry import RESOURCES, resource_admin
from apps.merchant.schema import fields_schema, sections, readonly, display, value


class SuperAdminHostPermission(BasePermission):
    """Global administration is exposed only on the root/base domain."""

    def has_permission(self, request, view):
        if not is_platform_host(request) or getattr(request, "tenant", None) is not None:
            raise NotFound("Administração global não disponível neste domínio.")
        return True


class SuperAdminPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            raise NotAuthenticated("Sua sessão expirou. Entre novamente.")
        if not user.is_active or not user.is_staff or not user.is_superuser:
            raise PermissionDenied("Você não tem acesso à administração global.")
        return True


class SuperAdminSession(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"


class SuperAdminAPI(APIView):
    authentication_classes = [SuperAdminSession]
    permission_classes = [SuperAdminHostPermission, SuperAdminPermission]
    renderer_classes = [JSONRenderer]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


def notices(request):
    return [{"level": m.tags, "text": str(m)} for m in messages.get_messages(request)]


@method_decorator(sensitive_post_parameters("password"), name="dispatch")
class Session(SuperAdminAPI):
    permission_classes = [SuperAdminHostPermission]
    allow_password_change = True

    def get(self, request):
        user = request.user
        return Response(
            {
                "csrf": get_token(request),
                "authenticated": bool(
                    user.is_authenticated and user.is_active and user.is_staff and user.is_superuser
                ),
                "password_change_required": False,
                "store": "Administração global",
                "panel": "superadmin",
            }
        )

    def post(self, request):
        # SessionAuthentication does not check CSRF for anonymous logins.
        SessionAuthentication().enforce_csrf(request)
        raw = request._request
        form = SuperAdminAuthenticationForm(request=raw, data=request.data)
        if not form.is_valid():
            return Response(
                {"errors": form.errors, "detail": "Confira seus dados de acesso."},
                status=getattr(raw, "admin_login_status", 400),
            )
        login(raw, form.get_user())
        return Response(
            {
                "csrf": get_token(raw),
                "password_change_required": False,
            }
        )

    def delete(self, request):
        SessionAuthentication().enforce_csrf(request)
        logout(request._request)
        return Response({"detail": "Você saiu da conta."})


@method_decorator(
    sensitive_post_parameters("old_password", "new_password1", "new_password2"),
    name="dispatch",
)
class Password(SuperAdminAPI):
    allow_password_change = True

    def post(self, request):
        form = PasswordChangeForm(request.user, request.data)
        if not form.is_valid():
            return Response({"errors": form.errors}, status=400)
        user = form.save()
        update_session_auth_hash(request._request, user)
        return Response({"detail": "Senha alterada.", "csrf": get_token(request)})


class Dashboard(SuperAdminAPI):
    def get(self, request):
        resources = []
        groups = {}
        for key, (_, title, group) in RESOURCES.items():
            admin = resource_admin(key)
            if admin.has_module_permission(request._request) and admin.has_view_permission(request._request):
                resources.append({"key": key, "title": title, "group": group})
                groups[group] = groups.get(group, 0) + 1
        return Response(
            {
                "panel": "superadmin",
                "store": "Administração global",
                "resources": resources,
                "groups": groups,
                "stats": {"resources": len(resources)},
            }
        )


def guarded(request, resource, pk=None, operation="view"):
    raw = getattr(request, "_request", request)
    admin = resource_admin(resource)
    if not admin.has_module_permission(raw):
        raise PermissionDenied()
    obj = (
        get_object_or_404(admin.get_queryset(raw), pk=pk)
        if pk is not None
        else None
    )
    check = getattr(admin, "has_" + operation + "_permission")
    allowed = check(raw) if operation == "add" else check(raw, obj)
    if not allowed:
        raise PermissionDenied("Esta ação não está disponível para seu acesso.")
    return admin, obj


def form_bundle(admin, raw, obj, bound=False):
    kwargs = {"instance": obj}
    if bound:
        kwargs.update(data=raw.POST, files=raw.FILES)
    form = admin.get_form(raw, obj)(**kwargs)
    formsets, inlines = admin._create_formsets(
        raw, form.instance, change=obj is not None
    )
    return form, formsets, inlines


def bundle_schema(admin, raw, obj, form, formsets, inlines):
    groups = []
    for fs, inline in zip(formsets, inlines):
        groups.append(
            {
                "title": str(inline.verbose_name_plural),
                "prefix": fs.prefix,
                "management": fields_schema(fs.management_form),
                "errors": list(fs.non_form_errors()),
                "can_add": inline.has_add_permission(raw, obj),
                "max": fs.max_num,
                "can_delete": fs.can_delete and inline.has_delete_permission(raw, obj),
                "forms": [
                    {
                        "fields": fields_schema(f),
                        "readonly": readonly(inline, raw, f.instance),
                        "errors": list(f.non_field_errors()),
                    }
                    for f in fs.forms
                ],
                "empty": {
                    "fields": fields_schema(fs.empty_form),
                    "readonly": [],
                    "errors": [],
                },
            }
        )
    return {
        "id": obj.pk if obj else None,
        "title": str(obj) if obj else "Novo cadastro",
        "fields": fields_schema(form),
        "sections": sections(admin, raw, obj),
        "readonly": readonly(admin, raw, obj),
        "inlines": groups,
        "errors": list(form.non_field_errors()),
        "can_save": (
            admin.has_change_permission(raw, obj)
            if obj
            else admin.has_add_permission(raw)
        ),
        "can_delete": bool(obj and admin.has_delete_permission(raw, obj)),
    }


class ResourceList(SuperAdminAPI):
    def get(self, request, resource):
        admin, _ = guarded(request, resource)
        raw = request._request
        from django.contrib.admin.options import IncorrectLookupParameters

        try:
            from apps.merchant.pagination import paged_admin
            admin = paged_admin(admin, raw)
            cl = admin.get_changelist_instance(raw)
        except (IncorrectLookupParameters, ValueError):
            return Response({"detail": "Filtro inválido."}, status=400)
        columns = [n for n in cl.list_display if n != "action_checkbox"]
        filters = [
            {
                "title": str(f.title),
                "options": [
                    {
                        "label": str(c["display"]),
                        "query": c["query_string"],
                        "selected": c["selected"],
                    }
                    for c in f.choices(cl)
                ],
            }
            for f in cl.filter_specs
        ]
        actions = [
            {
                "name": k,
                "label": str(v[2])
                % {"verbose_name_plural": admin.opts.verbose_name_plural},
            }
            for k, v in admin.get_actions(raw).items()
        ]
        metrics = {}
        if resource == "orders":
            from datetime import timedelta
            from django.utils import timezone
            from django.db.models import Count, Sum, Avg, Q
            from apps.orders.models import OrderItem

            orders = admin.get_queryset(raw).filter(
                created_at__gte=timezone.now() - timedelta(days=30)
            )
            metrics = orders.aggregate(
                generated=Count("id"),
                whatsapp_opened=Count("id", filter=Q(whatsapp_opened_at__isnull=False)),
                revenue=Sum("total"),
                avg_ticket=Avg("total"),
            )
            metrics["conversion"] = (
                round(metrics["whatsapp_opened"] / metrics["generated"] * 100, 1)
                if metrics["generated"]
                else 0
            )
            metrics["revenue"] = str(metrics["revenue"] or 0)
            metrics["avg_ticket"] = str(metrics["avg_ticket"] or 0)
            metrics["top_products"] = list(
                OrderItem.objects.filter(order__in=orders)
                .values("name")
                .annotate(quantity=Sum("quantity"))
                .order_by("-quantity", "name")[:5]
            )
        from django.contrib.admin.templatetags.admin_list import (
            result_headers,
            date_hierarchy,
        )

        headers = [
            h
            for h in result_headers(cl)
            if "action-checkbox-column" not in h.get("class_attrib", "")
        ]
        return Response(
            {
                "date_hierarchy": date_hierarchy(cl),
                "metrics": metrics,
                "title": RESOURCES[resource][1],
                "columns": [
                    {
                        "name": n,
                        "label": str(label_for_field(n, admin.model, admin)),
                        "sort": headers[i].get("url_primary"),
                    }
                    for i, n in enumerate(columns)
                ],
                "rows": [
                    {"id": obj.pk, "values": [display(admin, obj, n) for n in columns]}
                    for obj in cl.result_list
                ],
                "page_size": cl.list_per_page,
                "count": cl.result_count,
                "pages": cl.paginator.num_pages,
                "page": cl.page_num,
                "filters": filters,
                "actions": actions,
                "can_add": admin.has_add_permission(raw),
                "can_list_edit": bool(
                    admin.list_editable and admin.has_change_permission(raw)
                ),
            }
        )


class ResourceDetail(SuperAdminAPI):
    def get(self, request, resource, pk=None):
        admin, obj = guarded(request, resource, pk, "view" if pk else "add")
        form, fss, ins = form_bundle(admin, request._request, obj)
        return Response(bundle_schema(admin, request._request, obj, form, fss, ins))

    @transaction.atomic
    def post(self, request, resource, pk=None):
        admin, obj = guarded(request, resource, pk, "change" if pk else "add")
        # Parse multipart before passing the original HttpRequest to Django forms.
        request.data
        raw = request._request
        if obj is not None:
            admin.model.objects.select_for_update().get(pk=obj.pk)
        form, fss, ins = form_bundle(admin, raw, obj, True)
        valid = form.is_valid()
        for fs, inline in zip(fss, ins):
            valid = fs.is_valid() and valid
            allowed_ids = {str(x.pk) for x in fs.get_queryset()}
            for f in fs.forms:
                submitted = raw.POST.get(f.add_prefix(fs.model._meta.pk.name))
                if submitted and submitted not in allowed_ids:
                    raise PermissionDenied(
                        "Registro relacionado não pertence a este cadastro."
                    )
                if f.has_changed():
                    if f.cleaned_data.get("DELETE"):
                        if not inline.has_delete_permission(raw, obj):
                            raise PermissionDenied()
                    elif submitted and not inline.has_change_permission(raw, obj):
                        raise PermissionDenied()
                    elif not submitted and not inline.has_add_permission(raw, obj):
                        raise PermissionDenied()
        if not valid:
            return Response(bundle_schema(admin, raw, obj, form, fss, ins), status=400)
        try:
            with transaction.atomic():
                saved = admin.save_form(raw, form, change=obj is not None)
                admin.save_model(raw, saved, form, change=obj is not None)
                admin.save_related(raw, form, fss, change=obj is not None)
                change_message = admin.construct_change_message(
                    raw, form, fss, obj is None
                )
                if obj is None:
                    admin.log_addition(raw, saved, change_message)
                else:
                    admin.log_change(raw, saved, change_message)
        except (ValidationError, IntegrityError):
            return Response(
                {
                    "detail": "Não foi possível salvar. Confira os dados e possíveis registros duplicados."
                },
                status=400,
            )
        return Response(
            {"id": saved.pk, "detail": "Cadastro salvo.", "messages": notices(raw)}
        )

    @transaction.atomic
    def delete(self, request, resource, pk):
        admin, obj = guarded(request, resource, pk, "delete")
        deleted, counts, perms, protected = admin.get_deleted_objects(
            [obj], request._request
        )
        if perms or protected:
            return Response(
                {
                    "detail": "Este registro possui vínculos que impedem a exclusão.",
                    "protected": [str(x) for x in protected],
                },
                status=400,
            )
        if request.query_params.get("confirm") != "yes":
            return Response(
                {"confirmation_required": True, "objects": deleted, "counts": counts}
            )
        admin.log_deletions(request._request, [obj])
        admin.delete_model(request._request, obj)
        return Response({"detail": "Cadastro excluído."})


class ResourceAction(SuperAdminAPI):
    @transaction.atomic
    def post(self, request, resource):
        admin, _ = guarded(request, resource, operation="change")
        data = request.data
        raw = request._request
        name = data.get("action")
        actions = admin.get_actions(raw)
        if name not in actions:
            raise PermissionDenied()
        ids = data.getlist("ids") if hasattr(data, "getlist") else data.get("ids", [])
        if not isinstance(ids, list) or not ids or len(ids) > 500:
            return Response({"detail": "Selecione de 1 a 500 registros."}, status=400)
        try:
            qs = admin.get_queryset(raw).filter(pk__in=ids)
        except (ValueError, TypeError):
            return Response({"detail": "Seleção inválida."}, status=400)
        if qs.count() != len(set(map(str, ids))):
            raise Http404
        if any(not admin.has_change_permission(raw, obj) for obj in qs):
            raise PermissionDenied()
        if name == "delete_selected":
            if any(not admin.has_delete_permission(raw, obj) for obj in qs):
                raise PermissionDenied()
            deleted, counts, perms, protected = admin.get_deleted_objects(qs, raw)
            if perms or protected:
                return Response(
                    {"detail": "Há registros protegidos contra exclusão."}, status=400
                )
            if data.get("confirmed") != "yes":
                return Response(
                    {
                        "confirmation_required": True,
                        "objects": deleted,
                        "counts": counts,
                    }
                )
            admin.log_deletions(raw, qs)
            admin.delete_queryset(raw, qs)
        else:
            if name == "cancel_orders":
                if data.get("confirmed") != "yes":
                    return Response(
                        {
                            "confirmation_required": True,
                            "objects": [
                                "Cancelar pedidos e devolver estoque: "
                                + ", ".join(map(str, ids))
                            ],
                        }
                    )
                raw.POST = raw.POST.copy()
                raw.POST["confirm_cancel"] = "1"
            actions[name][0](admin, raw, qs)
        return Response({"detail": "Ação concluída.", "messages": notices(raw)})


class History(SuperAdminAPI):
    def get(self, request, resource, pk):
        from django.contrib.admin.models import LogEntry
        from django.contrib.contenttypes.models import ContentType
        from django.core.paginator import Paginator

        admin, obj = guarded(request, resource, pk)
        entries = (
            LogEntry.objects.filter(
                content_type=ContentType.objects.get_for_model(admin.model),
                object_id=str(obj.pk),
            )
            .select_related("user")
            .order_by("-action_time")
        )
        from apps.merchant.pagination import page_size
        page = Paginator(entries, page_size(request)).get_page(request.query_params.get("page"))
        return Response(
            {
                "rows": [
                    {
                        "date": value(e.action_time),
                        "user": str(e.user),
                        "action": e.get_change_message(),
                    }
                    for e in page
                ],
                "page": page.number,
                "pages": page.paginator.num_pages,
            }
        )


class ListEdit(SuperAdminAPI):
    """Preserve the merchant's existing list_editable operations and hooks."""

    def get_bundle(self, request, resource, bound=False):
        admin, _ = guarded(request, resource, operation="change")
        if not admin.list_editable:
            raise PermissionDenied("Esta lista não permite edição rápida.")
        raw = request._request
        from django.contrib.admin.options import IncorrectLookupParameters

        try:
            from apps.merchant.pagination import paged_admin
            admin = paged_admin(admin, raw)
            cl = admin.get_changelist_instance(raw)
        except (IncorrectLookupParameters, ValueError):
            raise PermissionDenied("Filtro inválido.")
        qs = cl.result_list
        kwargs = {"queryset": qs}
        if bound:
            kwargs.update(data=raw.POST, files=raw.FILES)
        fs = admin.get_changelist_formset(raw)(**kwargs)
        return admin, fs, qs

    def present(self, admin, fs):
        editable = set(admin.list_editable) | {admin.model._meta.pk.name}
        return {
            "title": str(admin.opts.verbose_name_plural),
            "management": fields_schema(fs.management_form),
            "errors": list(fs.non_form_errors()),
            "rows": [
                {
                    "title": str(f.instance),
                    "fields": [x for x in fields_schema(f) if x["name"] in editable],
                    "readonly": [],
                    "errors": list(f.non_field_errors()),
                }
                for f in fs.forms
            ],
        }

    def get(self, request, resource):
        admin, fs, _ = self.get_bundle(request, resource)
        return Response(self.present(admin, fs))

    @transaction.atomic
    def post(self, request, resource):
        request.data
        raw = request._request
        admin, fs, qs = self.get_bundle(request, resource, True)
        allowed_ids = {str(obj.pk) for obj in qs}
        seen = set()
        for form in fs.forms:
            pk = raw.POST.get(form.add_prefix(admin.model._meta.pk.name))
            if not pk or pk not in allowed_ids or pk in seen:
                raise PermissionDenied("A seleção foi alterada. Atualize a lista.")
            seen.add(pk)
            if not admin.has_change_permission(raw, form.instance):
                raise PermissionDenied()
        if seen != allowed_ids:
            return Response(
                {"detail": "A lista mudou. Atualize antes de salvar."}, status=409
            )
        if not fs.is_valid():
            return Response(self.present(admin, fs), status=400)
        # Lock only the current tenant's selected rows. Retain existing save hooks.
        list(admin.model.objects.filter(pk__in=seen).order_by("pk").select_for_update())
        for form in fs.forms:
            if form.has_changed():
                obj = admin.save_form(raw, form, change=True)
                admin.save_model(raw, obj, form, change=True)
                admin.save_related(raw, form, formsets=[], change=True)
                admin.log_change(
                    raw, obj, admin.construct_change_message(raw, form, None)
                )
        return Response(
            {"detail": "Alterações da página salvas.", "messages": notices(raw)}
        )
