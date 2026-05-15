from datetime import timedelta
from pathlib import Path
from django.templatetags.static import static
from django.urls import reverse_lazy

from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('DJANGO_SECRET_KEY')
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = [h.strip() for h in config('ALLOWED_HOSTS', default='localhost').split(',')]

INSTALLED_APPS = [
    # Unfold DEVE vir antes do django.contrib.admin
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',

    'apps.tenants',
    'apps.accounts',
    'apps.stores',
    'apps.orders',
    'apps.whatsapp',
    'apps.ml_engine',
    'apps.branding',
    'apps.landing_pages',
]

MIDDLEWARE = [
    'apps.tenants.middleware.TenantMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.tenants.context_processors.tenant_brand',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('POSTGRES_DB'),
        'USER': config('POSTGRES_USER'),
        'PASSWORD': config('POSTGRES_PASSWORD'),
        'HOST': config('DATABASE_HOST', default='db'),
        'PORT': config('DATABASE_PORT', default=5432, cast=int),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Celery (apenas uma vez, usando config())
CELERY_BROKER_URL = config('REDIS_URL', default='redis://redis:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://redis:6379/0')

# Email
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.sendgrid.net')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='pedidos@seudominio.com')

# WhatsApp
WHATSAPP_API_VERSION = config('WHATSAPP_API_VERSION', default='v21.0')
WHATSAPP_WEBHOOK_VERIFY_TOKEN = config('WHATSAPP_WEBHOOK_VERIFY_TOKEN')

# Domínio
DOMAIN = config('DOMAIN')

# Celery Beat
from celery_schedule import CELERY_BEAT_SCHEDULE

# ─── Unfold ───────────────────────────────────────────────────────────────────
UNFOLD = {
    "SITE_TITLE": "Painel do Lojista",
    "SITE_HEADER": "Painel do Lojista",
    "SITE_SYMBOL": "store",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "COLORS": {
        "primary": {
            "50":  "250 245 255",
            "100": "243 232 255",
            "200": "233 213 255",
            "300": "216 180 254",
            "400": "192 132 252",
            "500": "168 85 247",
            "600": "147 51 234",
            "700": "126 34 206",
            "800": "107 33 168",
            "900": "88 28 135",
            "950": "59 7 100",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Catálogo",
                "separator": True,
                "items": [
                    {
                        "title": "Produtos",
                        "icon": "restaurant_menu",
                        "link": reverse_lazy("tenant_admin:stores_product_changelist"),
                    },
                    {
                        "title": "Categorias",
                        "icon": "category",
                        "link": reverse_lazy("tenant_admin:stores_category_changelist"),
                    },
                    {
                        "title": "Meio a Meio",
                        "icon": "join_full",
                        "link": reverse_lazy("tenant_admin:stores_halfproduct_changelist"),
                    },
                ],
            },
            {
                "title": "Configurações",
                "separator": True,
                "items": [
                    {
                        "title": "Usuários",
                        "icon": "person",
                        "link": reverse_lazy("tenant_admin:accounts_user_changelist"),
                    },
                    {
                        "title": "Aparência",
                        "icon": "palette",
                        "link": reverse_lazy("tenant_admin:tenants_brandconfig_changelist"),
                    },
                ],
            },
        ],
    },
}

UNFOLD_SUPER = {
    "SITE_TITLE": "Super Admin",
    "SITE_HEADER": "Painel Global",
    "SITE_SYMBOL": "admin_panel_settings",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "COLORS": {
        "primary": {
            "50":  "250 245 255",
            "100": "243 232 255",
            "200": "233 213 255",
            "300": "216 180 254",
            "400": "192 132 252",
            "500": "168 85 247",
            "600": "147 51 234",
            "700": "126 34 206",
            "800": "107 33 168",
            "900": "88 28 135",
            "950": "59 7 100",
        },
    },
    "SIDEBAR": {
        "show_search": False,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Gestão",
                "separator": False,
                "items": [
                    {
                        "title": "Tenants",
                        "icon": "store",
                        "link": "/superadmin/tenants/tenant/",
                    },
                    {
                        "title": "Usuários",
                        "icon": "person",
                        "link": "/superadmin/accounts/user/",
                    },
                ],
            },
        ],
    },
}

SESSION_COOKIE_DOMAIN = ".localhost"
CSRF_COOKIE_DOMAIN = ".localhost"
CSRF_TRUSTED_ORIGINS = [
    "http://*.localhost:8000",
]