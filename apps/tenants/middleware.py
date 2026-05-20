from .models import Tenant
import logging

logger = logging.getLogger(__name__)

class TenantMiddleware:
    logger.warning("TenantMiddleware initialized")
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        logger.warning(f"Processing request for path: {request.path} with host: {request.META.get('HTTP_HOST', '')}")
        if request.path.startswith('/superadmin'):
            request.tenant = None
            return self.get_response(request)

        host = request.META.get('HTTP_HOST', '')
        logger.warning(f"Extracted host: {host}")
        subdomain = host.split('.')[0]
        subdomain = subdomain.split('.')[0]

        try:
            tenant = Tenant.objects.get(slug=subdomain)
        except Tenant.DoesNotExist:
            tenant = None

        request.tenant = tenant
        response = self.get_response(request)
        logger.warning(f"Finished processing request for path: {request.path} with tenant: {tenant}")
        return response
