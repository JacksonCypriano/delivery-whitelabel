from .models import Tenant
import logging

logger = logging.getLogger(__name__)

class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Ignora lógica de tenant para admin e webhooks
        if request.path.startswith('/admin') or request.path.startswith('/webhooks'):
            request.tenant = None
            return self.get_response(request)

        host = request.META.get('HTTP_HOST', '')
        subdomain = host.split('.')[0]

        try:
            tenant = Tenant.objects.get(slug=subdomain)
        except Tenant.DoesNotExist:
            tenant = None

        request.tenant = tenant
        response = self.get_response(request)
        return response
