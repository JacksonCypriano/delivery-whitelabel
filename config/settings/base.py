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
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "apps.tenants.middleware.TenantMiddleware",
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

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

LANGUAGE_CODE = "pt-br"

USE_I18N = True

USE_L10N = True

UNFOLD = {
    "SITE_TITLE": "Painel",
    "SITE_HEADER": "Painel Admin",
    "SITE_SUBHEADER": "Gestão da sua loja",
    "SITE_DROPDOWN": [
        {
            "icon": "diamond",
            "title": _("My site"),
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
                ],
            },
            {
                "title": _("Personalizações"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Rótulos"),
                        "icon": "label",
                        "link": reverse_lazy("tenant_admin:stores_customizationgrouplabel_changelist"),
                    },
                    {
                        "title": _("Grupos de Personalização"),
                        "icon": "tune",
                        "link": reverse_lazy("tenant_admin:stores_customizationgroup_changelist"),
                    },
                ],
            },
            {
                "title": _("Entrega"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Zonas de Entrega"),
                        "icon": "local_shipping",
                        "link": reverse_lazy("tenant_admin:tenants_deliveryzone_changelist"),
                    },
                ],
            },
            {
                "title": _("Pedidos"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Pedidos"),
                        "icon": "receipt_long",
                        "link": reverse_lazy("tenant_admin:orders_order_changelist"),
                    },
                ],
            },
            {
                "title": _("Configurações"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Minha Loja"),
                        "icon": "store",
                        "link": reverse_lazy("tenant_admin:tenants_tenant_changelist"),
                    },
                ],
            },
        ],
    }
}

UNFOLD_SUPER = {
    "SITE_TITLE": "Super Admin",
    "SITE_HEADER": "Painel Global",
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
