import uuid
from datetime import date
from django import forms
from django.core import signing
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Sum, Max
from django.utils import timezone
from rest_framework.response import Response
from apps.billing.models import Subscription, Invoice, FreeAccessGrant
from apps.billing.services import get_subscription
from apps.billing.free_access import (
    period,
    grant_free_days,
    access_state,
    existing_grant,
)
from apps.billing.provider import BillingError
from apps.merchant.schema import value, fields_schema
from .api import SuperAdminAPI, guarded


class FreeDaysForm(forms.Form):
    days = forms.IntegerField(label="Quantidade de dias gratuitos", min_value=1)
    reason = forms.CharField(
        label="Justificativa", max_length=500, widget=forms.Textarea
    )
    token = forms.UUIDField(widget=forms.HiddenInput)


def grant_json(grant):
    return {
        "operation_id": str(grant.pk),
        "days": grant.days,
        "reason": grant.reason,
        "date": value(grant.created_at),
        "actor": str(grant.actor),
        "previous": value(grant.previous_until),
        "start": value(grant.starts_on),
        "end": value(grant.ends_on),
        "access_before": grant.access_before,
        "access_after": grant.access_after,
    }


def impact(sub):
    tenant = sub.tenant
    blocked = (
        sub.manually_blocked
        or sub.payment_review
        or (not tenant.is_active and not sub.billing_suspended)
    )
    pending = (
        Invoice.objects.filter(tenant=tenant)
        .exclude(status__in=["PAID", "CANCELLED", "REFUNDED"])
        .count()
    )
    return {
        "blocked": blocked,
        "pending_invoices": pending,
        "access": (
            "A loja continuará bloqueada por motivo independente da validade."
            if blocked
            else "Acesso liberado pelo prazo concedido; suspensão por vencimento será removida."
        ),
        "billing": "Nenhuma cobrança será criada, quitada ou cancelada. Débitos existentes permanecem. Recorrências eventualmente configuradas no Asaas não são suspensas por esta concessão; confira-as no provedor.",
    }


class FreeDays(SuperAdminAPI):
    def get(self, request, pk):
        _, tenant = guarded(request, "tenants-tenant", pk, "change")
        sub = get_subscription(tenant)
        grants = sub.free_grants.select_related("actor")
        page = Paginator(grants, 20).get_page(request.query_params.get("page"))
        last = (
            Invoice.objects.filter(tenant=tenant, status="PAID")
            .order_by("-paid_at")
            .first()
        )
        return Response(
            {
                "tenant": str(tenant),
                "subscription_id": sub.pk,
                "plan": last.plan_name if last else "Sem plano pago registrado",
                "status": sub.situation,
                "valid_until": value(sub.valid_until),
                "active": tenant.is_active,
                "free_until": value(
                    grants.filter(ends_on__gt=timezone.localdate()).aggregate(
                        end=Max("ends_on")
                    )["end"]
                ),
                "total_days": grants.aggregate(total=Sum("days"))["total"] or 0,
                "fields": fields_schema(FreeDaysForm(initial={"token": uuid.uuid4()})),
                "impact": impact(sub),
                "history": [grant_json(g) for g in page],
                "page": page.number,
                "pages": page.paginator.num_pages,
            }
        )

    @transaction.atomic
    def post(self, request, pk):
        _, tenant = guarded(request, "tenants-tenant", pk, "change")
        get_subscription(tenant)
        sub = (
            Subscription.objects.select_for_update()
            .select_related("tenant")
            .get(tenant=tenant)
        )
        form = FreeDaysForm(request.data)
        if not form.is_valid():
            return Response(
                {
                    "detail": "Confira os campos da concessão.",
                    "fields": fields_schema(form),
                },
                status=400,
            )
        data = form.cleaned_data
        try:
            prior = existing_grant(
                data["token"], sub, data["days"], data["reason"], request.user
            )
            if prior:
                return Response(
                    {"detail": "Concessão já registrada.", "grant": grant_json(prior)}
                )
            start, end = period(sub, data["days"])
            payload = {
                "tenant": tenant.pk,
                "actor": request.user.pk,
                "days": data["days"],
                "reason": data["reason"],
                "token": str(data["token"]),
                "previous": value(sub.valid_until),
                "start": value(start),
                "end": value(end),
                "state": access_state(sub, sub.tenant),
            }
            preview = request.data.get("preview")
            if not preview:
                return Response(
                    {
                        "preview": signing.dumps(payload, salt="free-days"),
                        **payload,
                        "impact": impact(sub),
                    }
                )
            if signing.loads(preview, salt="free-days", max_age=900) != payload:
                return Response(
                    {
                        "detail": "Os dados ou o acesso mudaram. Confira uma nova prévia."
                    },
                    status=409,
                )
            grant = grant_free_days(
                tenant,
                data["days"],
                data["reason"],
                request.user,
                data["token"],
                sub.valid_until,
                True,
            )
        except IntegrityError:
            transaction.set_rollback(True)
            return Response(
                {"detail": "Identificador já utilizado. Gere uma nova concessão."},
                status=409,
            )
        except signing.BadSignature:
            return Response({"detail": "Prévia inválida ou expirada."}, status=409)
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {"detail": "Dias gratuitos concedidos.", "grant": grant_json(grant)}
        )


def creation_fields(form):
    form.fields["free_days"] = forms.IntegerField(
        label="Dias gratuitos iniciais (opcional)",
        required=False,
        min_value=1,
        max_value=(date.max - timezone.localdate()).days,
    )
    form.fields["free_days_reason"] = forms.CharField(
        label="Justificativa da gratuidade em dias",
        required=False,
        max_length=500,
        widget=forms.Textarea,
    )
    form.fields["free_days_token"] = forms.UUIDField(
        widget=forms.HiddenInput, initial=uuid.uuid4, required=False
    )
