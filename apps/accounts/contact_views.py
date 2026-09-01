from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from apps.customers.models import Customer
from .contact_otp import cancel_contact_change, pending_changes, send_contact_code, verify_contact_code
from .models import PendingContactChange
from .otp import OTPError, client_ip


def open_contact_change(request, pending):
    """Called only after a POST: GET must never trigger delivery."""
    if not pending.code_hash:
        try:
            send_contact_code(request.user.pk, pending.pk, client_ip(request))
            messages.success(request, f"Enviamos um código para confirmar seu novo {pending.get_channel_display()}.")
        except OTPError as exc:
            messages.error(request, str(exc))
    return redirect("customer_accounts:verify-contact", change_id=pending.pk)


@sensitive_post_parameters("code")
@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def customer_verify_contact(request, change_id):
    get_object_or_404(Customer, user=request.user)
    pending = get_object_or_404(PendingContactChange, pk=change_id, user=request.user)
    if pending.completed_at or pending.cancelled_at or pending.expires_at <= timezone.now():
        messages.info(request, "Esta solicitação expirou ou já foi encerrada. Seus contatos atuais estão disponíveis em Meus dados.")
        return redirect("customer_accounts:profile")
    if request.method == "POST":
        try:
            action = request.POST.get("action")
            if action == "cancel":
                cancel_contact_change(request.user.pk, pending.pk)
                messages.success(request, "Solicitação cancelada. Seu contato atual foi mantido.")
                return redirect("customer_accounts:profile")
            if action == "send":
                send_contact_code(request.user.pk, pending.pk, client_ip(request))
                messages.success(request, "Código enviado. Confira suas mensagens.")
            elif action == "verify":
                channel = verify_contact_code(request.user.pk, pending.pk, request.POST.get("code", "").strip())
                text = ("E-mail confirmado e atualizado! Use o novo e-mail no próximo login."
                        if channel == "email" else "WhatsApp confirmado e atualizado!")
                messages.success(request, text)
                following = pending_changes(request.user).first()
                if following:
                    return open_contact_change(request, following)
                return redirect("customer_accounts:profile")
            else:
                raise OTPError("Ação inválida.")
        except OTPError as exc:
            messages.error(request, str(exc))
        return redirect("customer_accounts:verify-contact", change_id=pending.pk)
    remaining = 0
    if pending.last_sent_at:
        remaining = max(0, 60 - int((timezone.now() - pending.last_sent_at).total_seconds()))
    return render(request, "accounts/customer_verify_contact.html", {
        "pending": pending, "resend_seconds": remaining,
    })
