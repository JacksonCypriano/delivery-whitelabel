import os
from pathlib import Path

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

DEBUG = False

CUSTOMER_PORTAL_URL = os.getenv("CUSTOMER_PORTAL_URL", "http://lvh.me:8000").rstrip("/")

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost").split(",") if h.strip()
]

TENANT_BASE_DOMAIN = os.getenv(
    "TENANT_BASE_DOMAIN",
    "lvh.me:8000",
).strip()

TENANT_PUBLIC_SCHEME = os.getenv(
    "TENANT_PUBLIC_SCHEME",
    "http",
).strip()

INSTALLED_APPS = [
    # third-party
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",

    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",

    # django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # local apps
    "apps.core",
    "apps.integrations.apps.IntegrationsConfig",
    "apps.billing.apps.BillingConfig",
    "apps.tenants",
    "apps.accounts",
    "apps.stores",
    "apps.orders",
    "apps.checkout",
    "apps.frontend",
    "apps.customers",
    "apps.coupons",
    "apps.marketplace.apps.MarketplaceConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.observability.RequestContextMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.audit.AuditContextMiddleware",

    "apps.tenants.middleware.TenantMiddleware",
    "apps.tenants.middleware.ForceInitialPasswordChangeMiddleware",
    "apps.marketplace.middleware.GlobalDeliveryLocationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"

# Banco
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("DATABASE_HOST"),
        "PORT": os.getenv("DATABASE_PORT"),
    }
}

# Static / Media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Celery
CELERY_BROKER_URL = os.getenv("REDIS_URL")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL")

LANGUAGE_CODE = "pt-br"

TIME_ZONE = "America/Sao_Paulo"

USE_I18N = True
USE_TZ = True

# Templates
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.contrib.messages.context_processors.messages",
                # Disponibiliza `tenant` e `cart_count_global` em todos os templates
                "apps.tenants.context_processors.tenant_brand",
                "apps.core.context_processors.global_settings",
            ],
        },
    },
]

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("CACHE_REDIS_URL") or os.getenv("REDIS_URL", "redis://redis:6379/0"),
    }
}



# WhatsApp / Evolution API
EVOLUTION_WHATSAPP_VALIDATION_ENABLED = os.getenv("EVOLUTION_WHATSAPP_VALIDATION_ENABLED", "false").lower() in ("1", "true", "yes", "on")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "")
EVOLUTION_API_TIMEOUT = int(os.getenv("EVOLUTION_API_TIMEOUT", "4"))
EVOLUTION_CHECK_CACHE_SECONDS = int(os.getenv("EVOLUTION_CHECK_CACHE_SECONDS", "86400"))
EVOLUTION_MONITOR_ENABLED = os.getenv("EVOLUTION_MONITOR_ENABLED", "false").lower() in ("1", "true", "yes", "on")
EVOLUTION_AUTO_RECONNECT = os.getenv("EVOLUTION_AUTO_RECONNECT", "false").lower() in ("1", "true", "yes", "on")
EVOLUTION_MONITOR_ENVIRONMENT = os.getenv("EVOLUTION_MONITOR_ENVIRONMENT", "local")
EVOLUTION_WEBHOOK_TOKEN = os.getenv("EVOLUTION_WEBHOOK_TOKEN", "")
EVOLUTION_ALERT_EMAILS = [v.strip() for v in os.getenv("EVOLUTION_ALERT_EMAILS", "").split(",") if v.strip()]

# E-mail / recuperação de senha
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() in ("1", "true", "yes", "on")
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() in ("1", "true", "yes", "on")
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "VemDeDelivery <no-reply@vemdedelivery.com.br>")

# Tokens de recuperação expiram em 1 hora.
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", "3600"))

# Observabilidade
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
DJANGO_LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "WARNING").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {
            "()": "apps.core.observability.RequestContextFilter",
        },
    },
    "formatters": {
        "json": {
            "()": "apps.core.observability.JsonFormatter",
        },
    },
    "handlers": {
        "console_json": {
            "class": "logging.StreamHandler",
            "filters": ["request_context"],
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console_json"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console_json"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console_json"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console_json"],
            "level": "WARNING",
            "propagate": False,
        },
        "vemdedelivery": {
            "handlers": ["console_json"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

LANGUAGE_CODE = "pt-br"

USE_I18N = True

USE_L10N = True

UNFOLD = {
    "SITE_TITLE": "Painel",
    "SITE_HEADER": "Painel da loja",
    "SITE_SUBHEADER": "Gestão da sua loja",
    "SITE_DROPDOWN": [
        {
            "icon": "diamond",
            "title": _("Minha loja"),
            "link": "https://example.com",
        }
    ],
    "SITE_URL": "/",
    "SITE_ICON": {
        "light": "/static/images/icon-light.svg",
        "dark": "/static/images/icon-dark.svg",
    },

    "SITE_LOGO": {
        "light": "/static/images/logo-light.svg",
        "dark": "/static/images/logo-dark.svg",
    },
    "SITE_SYMBOL": "speed",
    "SITE_FAVICONS": [
        {
            "rel": "icon",
            "sizes": "32x32",
            "type": "image/svg+xml",
            "href": "/static/images/favicon.svg",
        },
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "SHOW_BACK_BUTTON": False,
    "SHOW_UI_WARNINGS": False,
    # "ENVIRONMENT": "sample_app.environment_callback",
    # "ENVIRONMENT_TITLE_PREFIX": "sample_app.environment_title_prefix_callback",
    # "DASHBOARD_CALLBACK": "sample_app.dashboard_callback",
    "THEME": "dark",
    # "LOGIN": {
    #     "image": "/static/sample/login-bg.jpg",
    #     "redirect_after": lambda request: reverse_lazy("admin:APP_MODEL_changelist"),
    #     "form": "app.forms.CustomLoginForm",
    # },
    "STYLES": [
        lambda request: "/static/css/admin.css",
    ],
    "BORDER_RADIUS": "6px",
    "COLORS": {
        "base": {
            "50": "oklch(98.5% .002 247.839)",
            "100": "oklch(96.7% .003 264.542)",
            "200": "oklch(92.8% .006 264.531)",
            "300": "oklch(87.2% .01 258.338)",
            "400": "oklch(70.7% .022 261.325)",
            "500": "oklch(55.1% .027 264.364)",
            "600": "oklch(44.6% .03 256.802)",
            "700": "oklch(37.3% .034 259.733)",
            "800": "oklch(27.8% .033 256.848)",
            "900": "oklch(21% .034 264.665)",
            "950": "oklch(13% .028 261.692)",
        },
        "primary": {
            "50": "oklch(97.7% .014 308.299)",
            "100": "oklch(94.6% .033 307.174)",
            "200": "oklch(90.2% .063 306.703)",
            "300": "oklch(82.7% .119 306.383)",
            "400": "oklch(71.4% .203 305.504)",
            "500": "oklch(62.7% .265 303.9)",
            "600": "oklch(55.8% .288 302.321)",
            "700": "oklch(49.6% .265 301.924)",
            "800": "oklch(43.8% .218 303.724)",
            "900": "oklch(38.1% .176 304.987)",
            "950": "oklch(29.1% .149 302.717)",
        },
        "font": {
            "subtle-light": "var(--color-base-500)",
            "subtle-dark": "var(--color-base-400)",
            "default-light": "var(--color-base-600)",
            "default-dark": "var(--color-base-300)",
            "important-light": "var(--color-base-900)",
            "important-dark": "var(--color-base-100)",
        },
    },
    "EXTENSIONS": {
        "modeltranslation": {
            "flags": {
                "en": "🇬🇧",
                "fr": "🇫🇷",
                "nl": "🇧🇪",
            },
        },
    },
    "SIDEBAR": {
        "show_search": False,
        "command_search": False,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Comece por aqui"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Minha loja"),
                        "icon": "store",
                        "link": reverse_lazy("tenant_admin:tenants_tenant_changelist"),
                    },
                    {
                        "title": _("Perfil público"),
                        "icon": "public",
                        "link": reverse_lazy("tenant_admin:marketplace_marketplaceprofile_changelist"),
                    },
                    {
                        "title": _("Identidade visual"),
                        "icon": "palette",
                        "link": reverse_lazy("tenant_admin:tenants_brandconfig_changelist"),
                    },
                    {
                        "title": _("Horários de funcionamento"),
                        "icon": "schedule",
                        "link": reverse_lazy("tenant_admin:tenants_businesshour_changelist"),
                    },
                    {
                        "title": _("Locais e taxas de entrega"),
                        "icon": "local_shipping",
                        "link": reverse_lazy("tenant_admin:tenants_deliveryzone_changelist"),
                    },
                ],
            },
            {
                "title": _("Cardápio"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Categorias"),
                        "icon": "category",
                        "link": reverse_lazy("tenant_admin:stores_category_changelist"),
                    },
                    {
                        "title": _("Produtos"),
                        "icon": "fastfood",
                        "link": reverse_lazy("tenant_admin:stores_product_changelist"),
                    },
                    {
                        "title": _("Grupos de personalização"),
                        "icon": "tune",
                        "link": reverse_lazy("tenant_admin:stores_customizationgroup_changelist"),
                    },
                    {
                        "title": _("Rótulos de personalização"),
                        "icon": "label",
                        "link": reverse_lazy("tenant_admin:stores_customizationgrouplabel_changelist"),
                    },
                ],
            },
            {
                "title": _("Operação"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Pedidos"),
                        "icon": "receipt_long",
                        "link": reverse_lazy("tenant_admin:orders_order_changelist"),
                    },
                    {
                        "title": _("Clientes"),
                        "icon": "groups",
                        "link": reverse_lazy("tenant_admin:customers_customer_changelist"),
                    },
                ],
            },
            {
                "title": _("Marketing"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Campanhas de cupons"),
                        "icon": "local_activity",
                        "link": reverse_lazy("tenant_admin:coupons_couponcampaign_changelist"),
                    },
                    {
                        "title": _("Usos de cupons"),
                        "icon": "history",
                        "link": reverse_lazy("tenant_admin:coupons_couponredemption_changelist"),
                    },
                ],
            },
            {
                "title": _("Financeiro"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Minha assinatura"),
                        "icon": "payments",
                        "link": reverse_lazy("tenant_admin:billing_dashboard"),
                    },
                ],
            },
        ],
    }
}

UNFOLD_SUPER = {
    "SITE_TITLE": "Administração global",
    "STYLES": [
        lambda request: "/static/css/admin.css",
    ],
    "SITE_HEADER": "Painel Global",
    "SITE_SUBHEADER": "Gestão do VemDeDelivery",
    "SHOW_UI_WARNINGS": False,
    "SIDEBAR": {
        "show_search": False,
        "command_search": False,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Lojas e acessos"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Cadastrar loja + usuário"),
                        "icon": "person_add",
                        "link": reverse_lazy("super_admin:tenants_tenant_add"),
                    },
                    {
                        "title": _("Lojas"),
                        "icon": "store",
                        "link": reverse_lazy("super_admin:tenants_tenant_changelist"),
                    },
                    {
                        "title": _("Usuários"),
                        "icon": "group",
                        "link": reverse_lazy("super_admin:accounts_user_changelist"),
                    },
                ],
            },
            {
                "title": _("Financeiro"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Assinaturas"),
                        "icon": "subscriptions",
                        "link": reverse_lazy("super_admin:billing_subscription_changelist"),
                    },
                    {
                        "title": _("Cobranças"),
                        "icon": "receipt_long",
                        "link": reverse_lazy("super_admin:billing_invoice_changelist"),
                    },
                    {
                        "title": _("Créditos e cortesias"),
                        "icon": "redeem",
                        "link": reverse_lazy("super_admin:billing_credit_changelist"),
                    },
                    {
                        "title": _("Planos"),
                        "icon": "sell",
                        "link": reverse_lazy("super_admin:billing_plan_changelist"),
                    },
                    {
                        "title": _("Serviços adicionais"),
                        "icon": "add_business",
                        "link": reverse_lazy("super_admin:billing_additionalservice_changelist"),
                    },
                    {
                        "title": _("Contas de pagamento"),
                        "icon": "account_balance",
                        "link": reverse_lazy("super_admin:billing_tenantpaymentaccount_changelist"),
                    },
                    {
                        "title": _("Configurações de cobrança"),
                        "icon": "settings",
                        "link": reverse_lazy("super_admin:billing_billingsettings_changelist"),
                    },
                ],
            },
            {
                "title": _("WhatsApp"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Painel Evolution API"),
                        "icon": "chat",
                        "link": reverse_lazy("super_admin:evolution_panel"),
                    },
                    {
                        "title": _("Estado da integração"),
                        "icon": "sync",
                        "link": reverse_lazy("super_admin:integrations_whatsappintegrationstate_changelist"),
                    },
                    {
                        "title": _("Eventos"),
                        "icon": "history",
                        "link": reverse_lazy("super_admin:integrations_whatsappintegrationevent_changelist"),
                    },
                    {
                        "title": _("Alertas"),
                        "icon": "notifications",
                        "link": reverse_lazy("super_admin:integrations_whatsappalert_changelist"),
                    },
                ],
            },
            {
                "title": _("Marketplace"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Categorias"),
                        "icon": "category",
                        "link": reverse_lazy("super_admin:marketplace_marketplacecategory_changelist"),
                    },
                ],
            },
            {
                "title": _("Auditoria e segurança"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Eventos de segurança"),
                        "icon": "security",
                        "link": reverse_lazy("super_admin:accounts_securityevent_changelist"),
                    },
                    {
                        "title": _("Auditoria financeira"),
                        "icon": "fact_check",
                        "link": reverse_lazy("super_admin:billing_billingaudit_changelist"),
                    },
                    {
                        "title": _("Eventos de cobrança"),
                        "icon": "event_note",
                        "link": reverse_lazy("super_admin:billing_billingevent_changelist"),
                    },
                ],
            },
        ],
    },
}

# Marketplace - reverse geocoding
MARKETPLACE_GEOCODER_ENABLED = (
    os.getenv(
        "MARKETPLACE_GEOCODER_ENABLED",
        "true",
    ).lower()
    == "true"
)

MARKETPLACE_GEOCODER_URL = os.getenv(
    "MARKETPLACE_GEOCODER_URL",
    "https://nominatim.openstreetmap.org/reverse",
).strip()

MARKETPLACE_GEOCODER_USER_AGENT = os.getenv(
    "MARKETPLACE_GEOCODER_USER_AGENT",
    "VemDeDelivery/1.0 (+https://vemdedelivery.com.br)",
).strip()

MARKETPLACE_GEOCODER_TIMEOUT = int(
    os.getenv("MARKETPLACE_GEOCODER_TIMEOUT", "4")
)

MARKETPLACE_GEOCODER_CACHE_SECONDS = int(
    os.getenv(
        "MARKETPLACE_GEOCODER_CACHE_SECONDS",
        "604800",
    )
)

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

MARKETPLACE_CEP_URL = "https://viacep.com.br/ws/{cep}/json/"
MARKETPLACE_CEP_TIMEOUT = 4
MARKETPLACE_CEP_CACHE_SECONDS = 60 * 60 * 24 * 30
MARKETPLACE_CEP_USER_AGENT = "VemDeDelivery/1.0"

# Enable only behind a proxy that overwrites X-Real-IP.
OTP_TRUST_PROXY_HEADERS = os.getenv("OTP_TRUST_PROXY_HEADERS", "false").lower() in ("1", "true", "yes", "on")

# Pacotes 11/12: confiar no IP informado somente por proxies conhecidos.
OTP_TRUSTED_PROXY_CIDRS = [v.strip() for v in os.getenv("OTP_TRUSTED_PROXY_CIDRS", "").split(",") if v.strip()]
ADMIN_LOGIN_WINDOW = max(60, int(os.getenv("ADMIN_LOGIN_WINDOW", "900")))
ADMIN_LOGIN_IP_LIMIT = max(1, int(os.getenv("ADMIN_LOGIN_IP_LIMIT", "50")))
ADMIN_LOGIN_ACCOUNT_LIMIT = max(1, int(os.getenv("ADMIN_LOGIN_ACCOUNT_LIMIT", "10")))


# Assinaturas: implantação inicial não emite cobranças nem suspende lojas.
BILLING_ENABLED = os.getenv("BILLING_ENABLED", "false").lower() in ("1", "true", "yes", "on")
ASAAS_ENVIRONMENT = os.getenv("ASAAS_ENVIRONMENT", "sandbox")
ASAAS_API_KEY = os.getenv("ASAAS_API_KEY", "")
NFSE_DOCUMENT_HOSTS = tuple(v.strip().lower() for v in os.getenv('NFSE_DOCUMENT_HOSTS', 'asaas.com,www.asaas.com,sandbox.asaas.com').split(',') if v.strip())
NFSE_SANDBOX_EMAIL_ENABLED = os.getenv('NFSE_SANDBOX_EMAIL_ENABLED', 'false').lower() in ('true', '1', 'yes')
ASAAS_WEBHOOK_TOKEN = os.getenv("ASAAS_WEBHOOK_TOKEN", "")
# URL pública HTTPS que receberá eventos de aprovação das subcontas. Quando
# vazia, a sincronização periódica continua funcionando como contingência.
ASAAS_WEBHOOK_URL = os.getenv("ASAAS_WEBHOOK_URL", "").strip()
from celery.schedules import crontab
CELERY_TIMEZONE = "America/Sao_Paulo"
CELERY_ENABLE_UTC = True
CELERY_BEAT_SCHEDULE = {
    **globals().get("CELERY_BEAT_SCHEDULE", {}),
    "evolution-monitor": {"task": "apps.integrations.tasks.monitor_whatsapp", "schedule": 60.0},
    "evolution-alerts": {"task": "apps.integrations.tasks.send_whatsapp_alerts", "schedule": 60.0},
    "billing-suspend-daily": {
        "task": "apps.billing.tasks.suspend_expired_subscriptions",
        "schedule": crontab(hour=6, minute=0),
    },
    "billing-reconcile": {
        "task": "apps.billing.tasks.reconcile_pending_payments",
        "schedule": crontab(minute="*/5"),
    },
    "billing-fiscal-reconcile": {
        "task": "apps.billing.tasks.reconcile_fiscal_invoices",
        "schedule": crontab(minute="*/5"),
    },
    "billing-nfse-documents": {
        "task": "apps.billing.tasks.retry_nfse_documents",
        "schedule": crontab(minute="*/5"),
    },
}
