from .base import *

DEBUG = True

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "lvh.me",
    ".lvh.me",
]

CUSTOMER_PORTAL_URL = "http://lvh.me:8000"

SESSION_COOKIE_DOMAIN = ".lvh.me"
CSRF_COOKIE_DOMAIN = ".lvh.me"

CSRF_TRUSTED_ORIGINS = [
    "http://lvh.me:8000",
    "http://*.lvh.me:8000",
]
