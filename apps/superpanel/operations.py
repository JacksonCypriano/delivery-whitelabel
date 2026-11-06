"""React adapters for the retained administrative workflows."""

import uuid
from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework.response import Response
from .api import SuperAdminAPI, guarded, notices
from apps.merchant.schema import fields_schema, value


class ManualCredit(SuperAdminAPI):
    def get(self, request, pk):
        from apps.billing.forms import ManualCreditForm

        _, sub = guarded(request, "billing-subscription", pk, "change")
        from apps.billing.models import Invoice

        last_invoice = (
            Invoice.objects.filter(tenant_id=sub.tenant_id, status="PAID")
            .order_by("-paid_at")
            .first()
        )
        form = ManualCreditForm(
            initial={"tenant_id": sub.tenant_id, "token": uuid.uuid4()}
        )
        return Response(
            {
                "fields": fields_schema(form),
                "tenant": str(sub.tenant),
                "free_days_url": f"/painel/tenants-tenant/{sub.tenant_id}/gratuidade",

                "valid_until": value(sub.valid_until),
                "status": sub.situation,
                "plan": (
                    last_invoice.plan_name
                    if last_invoice
                    else "Sem plano pago registrado"
                ),
                "manually_blocked": sub.manually_blocked,
                "payment_review": sub.payment_review,
            }
        )

    @transaction.atomic
    def post(self, request, pk):
        from apps.billing.forms import ManualCreditForm
        from apps.billing.models import Subscription, Credit
        from apps.billing.services import manual_credit, add_months, BillingError

        _, sub = guarded(request, "billing-subscription", pk, "change")
        sub = Subscription.objects.select_for_update().get(pk=sub.pk)
        form = ManualCreditForm(request.data)
        if not form.is_valid():
            return Response(
                {"errors": form.errors, "detail": "Confira meses e justificativa."},
                status=400,
            )
        data = form.cleaned_data
        if data["tenant_id"] != sub.tenant_id:
            return Response({"detail": "Assinatura inválida."}, status=400)
        today = timezone.localdate()
        start = (
            sub.valid_until if sub.valid_until and sub.valid_until > today else today
        )
        end = add_months(
            start, data["months"], sub.anchor_day if start != today else today.day
        )
        payload = {
            "subscription": str(sub.pk),
            "actor": request.user.pk,
            "tenant": sub.tenant_id,
            "token": str(data["token"]),
            "months": data["months"],
            "reason": data["reason"],
            "previous": value(sub.valid_until),
            "until": value(end),
        }
        if not request.data.get("preview"):
            return Response(
                {
                    "preview": signing.dumps(payload, salt="manual-credit-preview"),
                    "previous": value(sub.valid_until),
                    "until": value(end),
                    "months": data["months"],
                    "reason": data["reason"],
                }
            )
        try:
            preview = signing.loads(
                request.data["preview"], salt="manual-credit-preview", max_age=900
            )
        except signing.BadSignature:
            return Response(
                {"detail": "Prévia expirada. Confira novamente."}, status=409
            )
        existing = Credit.objects.filter(manual_token=data["token"]).first()
        if existing:
            if (
                existing.tenant_id != sub.tenant_id
                or existing.months != data["months"]
                or existing.reason != data["reason"]
                or preview["actor"] != request.user.pk
            ):
                return Response(
                    {"detail": "Chave de operação já utilizada."}, status=409
                )
            return Response(
                {
                    "detail": "Meses já registrados.",
                    "valid_until": value(existing.valid_until),
                }
            )
        if preview != payload:
            return Response(
                {"detail": "A assinatura ou os dados mudaram. Gere uma nova prévia."},
                status=409,
            )
        try:
            credit = manual_credit(
                sub.tenant, data["months"], data["reason"], request.user, data["token"]
            )
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {
                "detail": "Meses registrados com sucesso.",
                "valid_until": value(credit.valid_until),
            }
        )


class FiscalDownload(SuperAdminAPI):
    def get(self, request, resource, pk, kind):
        if resource not in ("billing-fiscalinvoice", "billing-municipalexport"):
            from django.http import Http404

            raise Http404
        admin, obj = guarded(request, resource, pk)
        if resource == "billing-municipalexport":
            if kind != "csv":
                from django.http import Http404

                raise Http404
            return admin.download(request._request, obj.pk)
        return admin.download(request._request, obj.pk, kind)


class Prospecting(SuperAdminAPI):
    def get(self, request):
        admin, _ = guarded(request, "prospecting-prospectingbatch")
        response = admin.changelist_view(request._request)
        context = response.context_data
        data = {
            key.removeprefix("prospecting_"): value(context[key])
            for key in (
                "prospecting_enabled",
                "prospecting_pending_count",
                "prospecting_sent_count",
                "prospecting_start_time",
                "prospecting_end_time",
                "prospecting_messages_per_minute",
                "prospecting_timezone",
                "prospecting_window_open",
                "prospecting_queue_name",
            )
        }
        data["weekdays"] = sorted(context["prospecting_weekdays"])
        data["batches"] = [
            {
                "id": b.pk,
                "filename": b.filename,
                "created_at": value(b.created_at),
                "status": b.board_status,
                "total": b.total_contacts,
                "contacted": b.board_contacted,
                "pending": b.board_pending,
                "issues": b.board_issues,
                "ignored": b.board_ignored,
            }
            for b in context["prospecting_board_batches"]
        ]
        return Response(data)

    def post(self, request):
        admin, _ = guarded(request, "prospecting-prospectingbatch")
        data = request.data
        if data.get("prospecting_action") not in {
            "import",
            "delete_batch",
            "save_settings",
            "start",
            "pause",
        }:
            return Response({"detail": "Operação inválida."}, status=400)
        if (
            data.get("prospecting_action") in {"start", "delete_batch"}
            and data.get("confirmed") != "yes"
        ):
            return Response(
                {
                    "confirmation_required": True,
                    "objects": [
                        (
                            "Iniciar os envios na janela configurada."
                            if data["prospecting_action"] == "start"
                            else "Remover o lote e cancelar os contatos ainda pendentes."
                        )
                    ],
                }
            )
        admin.changelist_view(request._request)
        result = notices(request._request)
        return Response(
            {"messages": result},
            status=400 if any(m["level"] == "error" for m in result) else 200,
        )


class Evolution(SuperAdminAPI):
    def present(self, request, response):
        context = response.context_data
        row = context["connection"]
        return Response(
            {
                "connection": (
                    {
                        name: value(getattr(row, name))
                        for name in (
                            "environment",
                            "instance",
                            "status",
                            "checked_at",
                            "attempts",
                            "manual_required",
                            "reason",
                            "next_attempt_at",
                        )
                    }
                    if row
                    else None
                ),
                "stale": bool(context["stale"]),
                "qr": context["qr"],
                "pair_allowed": bool(context["pair_allowed"]),
                "events": [
                    {
                        "date": value(e.created_at),
                        "kind": e.kind,
                        "description": e.description,
                    }
                    for e in context["events"]
                ],
                "alerts": [
                    {"date": value(a.created_at), "status": a.get_status_display()}
                    for a in context["alerts"]
                ],
                "messages": notices(request._request),
            }
        )

    def get(self, request):
        admin, _ = guarded(request, "integrations-whatsappintegrationstate")
        return self.present(request, admin.panel(request._request))

    def post(self, request):
        admin, _ = guarded(request, "integrations-whatsappintegrationstate")
        if request.data.get("action") not in {"check", "restart", "pair"}:
            return Response({"detail": "Operação inválida."}, status=400)
        response = admin.panel(request._request)
        if response.status_code == 302:
            return Response({"messages": notices(request._request)})
        return self.present(request, response)


@method_decorator(sensitive_post_parameters("password1", "password2"), name="dispatch")
class UserPassword(SuperAdminAPI):
    def get(self, request, pk):
        admin, user = guarded(request, "accounts-user", pk, "change")
        return Response(
            {
                "fields": fields_schema(admin.change_password_form(user)),
                "username": user.username,
            }
        )

    @transaction.atomic
    def post(self, request, pk):
        from django.contrib.auth import update_session_auth_hash

        admin, user = guarded(request, "accounts-user", pk, "change")
        form = admin.change_password_form(user, request.data)
        if not form.is_valid():
            return Response(
                {
                    "fields": fields_schema(form),
                    "detail": "Confira os campos da senha.",
                },
                status=400,
            )
        user = form.save()
        admin.log_change(request._request, user, "Senha alterada pelo administrador.")
        update_session_auth_hash(request._request, user)
        return Response({"detail": "Senha alterada."})
