"""Local smoke tests only. Homologation/critical acceptance requires PostgreSQL."""

from .test import *  # noqa: F403,F401

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
SECRET_KEY = "package-12-local-test-key-not-for-deployment"
EVOLUTION_WHATSAPP_VALIDATION_ENABLED = False
