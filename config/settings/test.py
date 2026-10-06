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

# O agente WhatsApp nunca usa rede externa durante testes.
WHATSAPP_AGENT_ENABLED = False
WHATSAPP_AGENT_WEBHOOK_URL = ""
WHATSAPP_AGENT_WEBHOOK_TOKEN = ""
WHATSAPP_AGENT_OLLAMA_ENABLED = False
# A suíte crítica cria e valida JWTs em sequência imediata. Em ambientes
# virtualizados/containers, pequenas correções do relógio do host podem fazer
# um token recém-emitido parecer alguns segundos "no futuro". O leeway é
# exclusivo dos testes e elimina essa dependência do relógio de parede sem
# alterar a configuração de produção.
SIMPLE_JWT = {"LEEWAY": 30}


# Hosts artificiais usados pelo Django test client para exercitar o fallback
# técnico do SuperAdmin. Não existe em produção e não amplia os hosts reais.
PLATFORM_ADMIN_HOST_ALIASES = ("testserver", "localhost")
