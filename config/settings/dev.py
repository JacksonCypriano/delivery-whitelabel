from .base import *

DEBUG = True

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "lvh.me",
    ".lvh.me",
]

CUSTOMER_PORTAL_URL = os.getenv("CUSTOMER_PORTAL_URL", "https://lvh.me").rstrip("/")
TENANT_BASE_DOMAIN = os.getenv("TENANT_BASE_DOMAIN", "lvh.me").strip()
TENANT_PUBLIC_SCHEME = os.getenv("TENANT_PUBLIC_SCHEME", "https").strip()

SESSION_COOKIE_DOMAIN = ".lvh.me"
CSRF_COOKIE_DOMAIN = ".lvh.me"

CSRF_TRUSTED_ORIGINS = [
    "https://lvh.me",
    "https://*.lvh.me",
    "http://lvh.me:8000",
    "http://*.lvh.me:8000",
]
