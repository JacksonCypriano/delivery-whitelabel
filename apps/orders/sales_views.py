from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods
from django.http import HttpResponseBadRequest, JsonResponse
from django.utils import timezone
from datetime import timedelta
from .models import SalesMessage, MarketingConsent, OrderFeedback
from apps.public_ui.rendering import render_public


@require_http_methods(["GET", "POST"])
def feedback(request, token):
    message = get_object_or_404(
        SalesMessage,
        token=token,
        tenant=getattr(request, "tenant", None),
        sent_at__isnull=False,
        created_at__gte=timezone.now() - timedelta(days=90),
    )
    done = False
    if request.method == "POST":
        if request.POST.get("action") == "unsubscribe":
            MarketingConsent.objects.filter(
                tenant=message.tenant, customer=message.customer
            ).update(allowed=False)
            done = True
        elif (
            message.kind == "feedback"
            and message.order
            and message.order.status == "delivered"
        ):
            try:
                rating = int(request.POST.get("rating", ""))
            except (ValueError, TypeError):
                return HttpResponseBadRequest("Informe uma nota de 1 a 5.")
            comment = request.POST.get("comment", "").strip()
            if not 1 <= rating <= 5 or len(comment) > 1000:
                return HttpResponseBadRequest("Confira a nota e o comentário.")
            OrderFeedback.objects.get_or_create(
                order=message.order,
                defaults={
                    "tenant": message.tenant,
                    "rating": rating,
                    "comment": comment,
                },
            )
            done = True
    return render_public(
        request, "sales/feedback", {"feedback_kind": message.kind, "done": done}
    )


@require_http_methods(["POST"])
def consent(request):
    if not request.user.is_authenticated or not getattr(request, "tenant", None):
        return JsonResponse({"error": "Entre na conta da loja."}, status=403)
    from apps.customers.models import Customer

    customer = get_object_or_404(Customer, user=request.user, phone_verified=True)
    MarketingConsent.objects.update_or_create(
        tenant=request.tenant,
        customer=customer,
        defaults={"allowed": request.POST.get("allowed") == "on"},
    )
    return redirect("checkout:cart")
