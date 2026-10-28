"""Homologacao publica isolada da producao.

Credenciais e banco devem vir exclusivamente de /opt/vemdedelivery/hml/config/.env.
Nunca habilitar pagamentos reais, mensageria real ou marketplaces live aqui.
"""

from django.core.exceptions import ImproperlyConfigured

from .prod import *

# Fail closed if a production database is accidentally supplied to homologacao.
if (
    os.getenv("POSTGRES_DB") != "delivery_hml"
    or os.getenv("POSTGRES_USER") != "delivery_hml"
    or os.getenv("DATABASE_HOST") != "db"
):
    raise ImproperlyConfigured("Homologacao exige banco delivery_hml no servico db.")

if os.getenv("ASAAS_ENVIRONMENT") != "sandbox":
    raise ImproperlyConfigured("Homologacao exige ASAAS_ENVIRONMENT=sandbox.")

if os.getenv("TENANT_BASE_DOMAIN") != "hml.vemdedelivery.com.br":
    raise ImproperlyConfigured("Homologacao exige TENANT_BASE_DOMAIN=hml.vemdedelivery.com.br.")

DEBUG = False

# HSTS do ambiente de producao nao deve abranger subdominios de homologacao.
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Protecoes adicionais contra efeitos em sistemas externos.
ASAAS_ENVIRONMENT = "sandbox"
BILLING_ALLOW_SANDBOX = True
BILLING_ENABLED = False
ASAAS_API_KEY = ""
WHATSAPP_AGENT_ENABLED = False
EVOLUTION_MONITOR_ENABLED = False
EVOLUTION_AUTO_RECONNECT = False
MARKETING_LEAD_TRACKING_ENABLED = False
MARKETPLACE_GEOCODER_ENABLED = False
CHANNELS_NETWORK_ENABLED = False
CHANNELS_LIVE_ENABLED = False
CHANNELS_SIMULATOR_ENABLED = False

# Nenhum envio por SMTP de testes.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Os workers e o scheduler nao sobem na etapa inicial.
# Deixamos as tarefas agendadas inertes mesmo se alguem iniciar Beat sem querer.
CELERY_BEAT_SCHEDULE = {}
