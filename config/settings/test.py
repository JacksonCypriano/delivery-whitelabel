from .base import *  # noqa: F403,F401

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", ".lvh.me", "vemdedelivery.com.br", ".vemdedelivery.com.br"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "critical-tests"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MARKETPLACE_GEOCODER_ENABLED = False

# Testes nunca utilizam credenciais reais herdadas do container.
BILLING_ENABLED = False
ASAAS_ENVIRONMENT = "sandbox"
ASAAS_API_KEY = ""
ASAAS_WEBHOOK_TOKEN = ""
