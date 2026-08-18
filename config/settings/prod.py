from .base import *

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()
]

# Domínio dos cookies compartilhado entre subdomínios (multi-tenant).
# Configurável via variável de ambiente SESSION_COOKIE_DOMAIN (ex.: .meudominio.com).
# Se não definido, o Django usa o comportamento padrão (cookie por host).
_COOKIE_DOMAIN = os.getenv("SESSION_COOKIE_DOMAIN", "").strip() or None
if _COOKIE_DOMAIN:
    SESSION_COOKIE_DOMAIN = _COOKIE_DOMAIN
    CSRF_COOKIE_DOMAIN = _COOKIE_DOMAIN
