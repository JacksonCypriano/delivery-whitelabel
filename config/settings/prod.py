from .base import *

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "true").lower() in ("1", "true", "yes", "on")
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]

_COOKIE_DOMAIN = os.getenv("SESSION_COOKIE_DOMAIN", "").strip() or None
if _COOKIE_DOMAIN:
    SESSION_COOKIE_DOMAIN = _COOKIE_DOMAIN
    CSRF_COOKIE_DOMAIN = _COOKIE_DOMAIN

CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]

CUSTOMER_PORTAL_URL = os.getenv("CUSTOMER_PORTAL_URL", "https://vemdedelivery.com.br").rstrip("/")
TENANT_BASE_DOMAIN = os.getenv("TENANT_BASE_DOMAIN", "vemdedelivery.com.br").strip()
TENANT_PUBLIC_SCHEME = os.getenv("TENANT_PUBLIC_SCHEME", "https").strip()

# Sentry é opcional: com SENTRY_DSN vazio, nenhuma informação é enviada.
SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("SENTRY_RELEASE") or None,
        send_default_pii=False,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        profiles_sample_rate=0.0,
    )


# Produção usa somente a API real; homologação permanece sandbox por padrão.
ASAAS_ENVIRONMENT = os.getenv("ASAAS_ENVIRONMENT", "production")
BILLING_ALLOW_SANDBOX = False
