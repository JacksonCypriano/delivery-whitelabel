from django.conf import settings


def global_settings(request):
    return {
        "CUSTOMER_PORTAL_URL": settings.CUSTOMER_PORTAL_URL,
    }
