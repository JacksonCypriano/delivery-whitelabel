import os
from pathlib import Path

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

DEBUG = False

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost").split(",") if h.strip()
]

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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",

    "apps.tenants.middleware.TenantMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
            ],
        },
    },
]

AUTH_USER_MODEL = "accounts.User"

SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None

SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

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
        # "navigation": [
        #     {
        #         "title": _("Navigation"),
        #         "separator": True,
        #         "collapsible": True,
        #         "items": [
        #             {
        #                 "title": _("Dashboard"),
        #                 "icon": "dashboard",
        #                 "link": reverse_lazy("admin:index"),
        #                 "badge": "sample_app.badge_callback",
        #                 "badge_variant": "info",
        #                 "badge_style": "solid",
        #                 "permission": lambda request: request.user.is_superuser,
        #             },
        #             {
        #                 "title": _("Users"),
        #                 "icon": "people",
        #                 "link": reverse_lazy("admin:auth_user_changelist"),
        #             },
        #         ],
        #     },
        # ],
    },
    # "TABS": [
    #     {
    #         "models": [
    #             "tenants.tenant",
    #             "stores.store",
    #         ],
    #         "items": [
    #             {
    #                 "title": _("Dashboard"),
    #                 "link": reverse_lazy("admin:index"),
    #             },
    #             {
    #                 "title": _("Tenants"),
    #                 "link": reverse_lazy("tenants_tenant_changelist")
    #             },
    #             {
    #                 "title": _("Stores"),
    #                 "link": reverse_lazy("stores_store_changelist"),
    #             },
    #         ],
    #     },
    # ],
}

UNFOLD_SUPER = {
    "SITE_TITLE": "Super Admin",
    "SITE_HEADER": "Painel Global",
}
