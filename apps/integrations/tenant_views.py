from datetime import timedelta

from django.contrib import messages
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables

from apps.integrations.whatsapp.client import EvolutionError
from apps.integrations.whatsapp_agent.connection import (
    connect_agent,
    disconnect_agent,
    feature_enabled,
    get_or_create_agent,
    refresh_agent,
)


@never_cache
@sensitive_variables()
def tenant_whatsapp_agent_panel(request):
    tenant = getattr(request, "tenant", None)
    if not tenant or not request.user.is_authenticated or request.user.tenant_id != tenant.id:
        raise PermissionDenied
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])

    agent = get_or_create_agent(tenant)
    qr = None

    if request.method == "GET" and request.GET.get("format") == "status":
        agent.refresh_from_db()
        return JsonResponse({
            "status": agent.status,
            "status_display": agent.get_status_display(),
            "ai_enabled": agent.ai_enabled,
            "requires_pairing": agent.requires_pairing,
            "checked_at": agent.checked_at.isoformat() if agent.checked_at else None,
            "webhook_at": agent.webhook_at.isoformat() if agent.webhook_at else None,
        })

    if request.method == "POST":
        action = request.POST.get("action", "")
        if not feature_enabled():
            messages.error(request, "O atendimento inteligente ainda não está habilitado neste ambiente.")
        else:
            try:
                if action == "connect":
                    qr = connect_agent(agent)
                    agent.refresh_from_db()
                    if qr:
                        messages.info(request, "Escaneie o QR Code com o WhatsApp da loja. O código não será armazenado.")
                    else:
                        messages.success(request, "O WhatsApp da loja já está conectado.")
                elif action == "check":
                    refresh_agent(agent)
                    agent.refresh_from_db()
                    messages.success(request, "Situação do WhatsApp atualizada.")
                elif action == "disconnect":
                    disconnect_agent(agent)
                    agent.refresh_from_db()
                    messages.success(
                        request,
                        "WhatsApp desconectado. Para usar novamente, gere um novo QR Code.",
                    )
                elif action == "toggle":
                    agent.refresh_from_db()
                    enabling = not agent.ai_enabled
                    if enabling and agent.status != agent.Status.OPEN:
                        messages.error(request, "Conecte o WhatsApp antes de ativar o agente de atendimento.")
                    else:
                        agent.ai_enabled = enabling
                        agent.save(update_fields=("ai_enabled", "updated_at"))
                        messages.success(
                            request,
                            "Agente de atendimento ativado." if enabling else "Agente de atendimento desativado.",
                        )
                else:
                    messages.error(request, "Ação inválida.")
            except EvolutionError:
                messages.error(
                    request,
                    "Não foi possível concluir a operação com o WhatsApp. Confira a configuração ou tente novamente.",
                )
        if qr is None:
            return redirect("tenant_admin:whatsapp_agent")

    stale = bool(
        agent.checked_at
        and timezone.now() - agent.checked_at > timedelta(minutes=3)
    )
    # Custom admin views precisam receber o mesmo contexto do TenantAdminSite.
    # Sem isso o Unfold perde sidebar, cabeçalho, identidade da loja e demais
    # elementos que aparecem nas telas administrativas padrão.
    from apps.tenants.admin_site import tenant_admin_site

    context = {
        **tenant_admin_site.each_context(request),
        "title": "Atendimento WhatsApp",
        "agent": agent,
        "feature_enabled": feature_enabled(),
        "stale": stale,
        "qr": qr,
        "events": agent.events.all()[:25],
        "back_url": reverse("tenant_admin:index"),
        "context_timeout_minutes": getattr(
            settings, "WHATSAPP_AGENT_CONTEXT_TIMEOUT_MINUTES", 45
        ),
    }
    response = TemplateResponse(request, "admin/tenant/whatsapp_agent.html", context)
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response
