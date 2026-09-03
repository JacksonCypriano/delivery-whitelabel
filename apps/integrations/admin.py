import base64
import binascii
from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables
from unfold.admin import ModelAdmin

from apps.tenants.admin_site import super_admin_site
from .models import WhatsAppIntegrationState, WhatsAppIntegrationEvent, WhatsAppAlert
from .whatsapp.client import EvolutionClient, EvolutionError
from .whatsapp.monitor import (
    current_state,
    enabled,
    identity,
    request_action,
    claim,
    release,
    locked,
    apply_observation,
)
from django.db import transaction


class SuperOnly(ModelAdmin):
    def has_module_permission(self, request):
        return super_admin_site.has_permission(request)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WhatsAppIntegrationState, site=super_admin_site)
class ConnectionAdmin(SuperOnly):
    list_display = (
        "__str__",
        "status",
        "checked_at",
        "observed_online_at",
        "manual_required",
        "panel_link",
    )
    readonly_fields = tuple(
        field.name for field in WhatsAppIntegrationState._meta.fields
    )
    fields = (
        "environment",
        "instance",
        "status",
        "checked_at",
        "observed_online_at",
        "online_since",
        "webhook_at",
        "down_since",
        "attempts",
        "next_attempt_at",
        "manual_required",
        "reason",
    )
    list_filter = ("environment", "status", "manual_required")

    @admin.display(description="Operações")
    def panel_link(self, obj):
        if obj.identity == identity():
            return format_html(
                '<a href="{}">Abrir painel</a>', reverse("super_admin:evolution_panel")
            )
        return "Configuração anterior — somente histórico"

    def get_urls(self):
        return [
            path(
                "painel/",
                self.admin_site.admin_view(self.panel),
                name="evolution_panel",
            )
        ] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        if enabled():
            current_state()
        else:
            messages.info(
                request, "Monitoramento WhatsApp desabilitado neste ambiente."
            )
        return super().changelist_view(request, extra_context)

    @method_decorator(never_cache)
    @sensitive_variables()
    def panel(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        request.current_app = self.admin_site.name
        if request.method not in {"GET", "POST"}:
            return HttpResponseNotAllowed(["GET", "POST"])
        qr = None
        if request.method == "POST":
            action = request.POST.get("action", "")
            try:
                request_action(action, request.user)
                if action == "pair":
                    reservation = claim()
                    if not reservation:
                        raise EvolutionError("rate_limit")
                    pk, token = reservation
                    try:
                        client = EvolutionClient()
                        status = client.status()
                        # No connect request while already open. An expired hint
                        # alone never authorizes a disconnect/replacement session.
                        if status == "open":
                            with transaction.atomic():
                                row = locked(pk, token)
                                if row:
                                    apply_observation(row, "open")
                            messages.success(request, "A instância já está conectada.")
                        else:
                            data = client.connect()
                            candidate = (
                                data.get("base64") if isinstance(data, dict) else None
                            )
                            if (
                                not candidate
                                and isinstance(data, dict)
                                and isinstance(data.get("qrcode"), dict)
                            ):
                                candidate = data["qrcode"].get("base64")
                            prefix = "data:image/png;base64,"
                            if (
                                not isinstance(candidate, str)
                                or len(candidate) > 350000
                                or not candidate.startswith(prefix)
                            ):
                                raise EvolutionError("invalid_response")
                            decoded = base64.b64decode(
                                candidate[len(prefix) :], validate=True
                            )
                            if not decoded.startswith(b"\x89PNG\r\n\x1a\n"):
                                raise EvolutionError("invalid_response")
                            qr = candidate
                            messages.info(
                                request,
                                "QR Code temporário. Escaneie somente com o número da plataforma. Ele não será salvo.",
                            )
                    finally:
                        release(pk, token)
                else:
                    from .tasks import monitor_whatsapp

                    try:
                        monitor_whatsapp.delay()
                        messages.success(
                            request,
                            "Solicitação registrada. Atualize a página em alguns segundos.",
                        )
                    except Exception:
                        messages.warning(
                            request,
                            "Solicitação registrada; aguardando o agendador. Verifique Celery e Redis.",
                        )
            except (EvolutionError, ValueError, binascii.Error):
                messages.error(
                    request,
                    "Operação não concluída. Confira o estado e a configuração; aguarde 60 segundos entre ações. O limite é de três reconexões por incidente.",
                )
            if qr is None:
                return redirect("super_admin:evolution_panel")
        row = current_state() if enabled() else None
        stale = row and (
            not row.checked_at or timezone.now() - row.checked_at > timedelta(minutes=3)
        )
        context = {
            **self.admin_site.each_context(request),
            "title": "WhatsApp / Evolution API",
            "opts": WhatsAppIntegrationState._meta,
            "connection": row,
            "stale": stale,
            "qr": qr,
            "events": row.events.select_related("actor")[:30] if row else [],
            "alerts": (
                WhatsAppAlert.objects.filter(state=row).order_by("-pk")[:10]
                if row
                else []
            ),
            "pair_allowed": row
            and row.status in {"pairing", "close", "connecting"}
            and row.manual_required,
        }
        response = TemplateResponse(
            request, "admin/integrations/whatsapp_panel.html", context
        )
        response["Cache-Control"] = "private, no-store, max-age=0"
        response["Referrer-Policy"] = "no-referrer"
        return response


@admin.register(WhatsAppIntegrationEvent, site=super_admin_site)
class EventAdmin(SuperOnly):
    list_display = ("created_at", "state", "description", "actor")
    list_filter = ("state",)
    fields = ("state", "created_at", "description", "actor", "incident")
    readonly_fields = tuple(
        field.name for field in WhatsAppIntegrationEvent._meta.fields
    )
    list_select_related = ("state", "actor")


@admin.register(WhatsAppAlert, site=super_admin_site)
class AlertAdmin(SuperOnly):
    list_display = (
        "created_at",
        "state",
        "recovery",
        "status",
        "attempted_at",
        "sent_at",
    )
    list_filter = ("state", "status", "recovery")
    readonly_fields = tuple(field.name for field in WhatsAppAlert._meta.fields)
