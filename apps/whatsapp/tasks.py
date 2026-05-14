import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='whatsapp.processar_mensagem')
def processar_mensagem_task(tenant_id, config_id, payload):
    from apps.tenants.models import Tenant
    from apps.whatsapp.models import WhatsAppConfig
    from apps.whatsapp.services import processar_mensagem_oficial

    try:
        tenant = Tenant.objects.get(id=tenant_id)
        config = WhatsAppConfig.objects.get(id=config_id)
        processar_mensagem_oficial(tenant, config, payload)
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}", exc_info=True)
