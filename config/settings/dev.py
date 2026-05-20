from .base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Email debug
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
