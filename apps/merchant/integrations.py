from django.http import Http404, JsonResponse
from rest_framework.response import Response
from .api import MerchantAPI, notices
from .navigation import react_url


class ExistingViewAPI(MerchantAPI):
    """Reuse each existing financial operation, with JSON presentation only."""

    def dispatch_existing(self, request, view, **kwargs):
        request.data
        raw = request._request
        raw.merchant_api = True
        response = view(raw, **kwargs)
        if response.status_code in (301, 302):
            return Response(
                {"redirect": react_url(response["Location"]), "messages": notices(raw)}
            )
        if isinstance(response, JsonResponse):
            import json

            payload = json.loads(response.content)
            payload["messages"] = notices(raw)
            return Response(payload, status=response.status_code)
        return response


class Finance(ExistingViewAPI):
    def get(self, request, action="dashboard", invoice_id=None, kind=None):
        from apps.billing import views

        mapping = {
            "dashboard": views.dashboard,
            "invoice": views.invoice_detail,
            "notes": views.fiscal_list,
            "fees": views.online_fees,
            "download": views.fiscal_download,
        }
        if action not in mapping:
            raise Http404
        kwargs = {}
        if invoice_id is not None:
            kwargs["invoice_id"] = invoice_id
        if kind is not None:
            kwargs["kind"] = kind
        return self.dispatch_existing(request, mapping[action], **kwargs)

    def post(self, request, action, invoice_id=None):
        from apps.billing import views

        if action not in ("purchase", "refresh"):
            raise Http404
        kwargs = {"invoice_id": invoice_id} if invoice_id is not None else {}
        return self.dispatch_existing(
            request, views.purchase if action == "purchase" else views.refresh, **kwargs
        )


class Whatsapp(ExistingViewAPI):
    def get(self, request):
        from apps.integrations.tenant_views import tenant_whatsapp_agent_panel

        return self.dispatch_existing(request, tenant_whatsapp_agent_panel)

    def post(self, request):
        from apps.integrations.tenant_views import tenant_whatsapp_agent_panel

        return self.dispatch_existing(request, tenant_whatsapp_agent_panel)
