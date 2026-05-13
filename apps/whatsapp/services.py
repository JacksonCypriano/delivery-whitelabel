import logging

from django.conf import settings

from .clients import WhatsAppClient
from .selectors import get_whatsapp_config_for_tenant
from apps.ml_engine.classifier import classificar

logger = logging.getLogger(__name__)


def get_base_url(tenant):
    if settings.DEBUG:
        return f"{tenant.slug}.localhost"
    return f"https://{tenant.slug}.{settings.DOMAIN}"


def get_store_link(tenant):
    return get_base_url(tenant)


def enviar_mensagem_texto(tenant, to_number: str, text_body: str):
    config = get_whatsapp_config_for_tenant(tenant)

    if not config:
        logger.error(f"Nenhuma config WhatsApp ativa para o tenant: {tenant}")
        return None

    client = WhatsAppClient(
        access_token=config.access_token,
        phone_number_id=config.phone_number_id,
    )

    return client.send_text_message(to_number, text_body)


def _resposta_saudacao(tenant):
    return (
        f"Olá! 👋 Seja bem-vindo à *{tenant.name}*!\n\n"
        f"Para fazer seu pedido, acesse nosso cardápio:\n"
        f"{get_store_link(tenant)}\n\n"
        f"É rápido e fácil! 🍔🛵"
    )


def _resposta_pedido(tenant):
    return (
        f"📲 Acesse nosso cardápio e faça seu pedido:\n"
        f"{get_store_link(tenant)}\n\n"
        f"Aceitamos pagamento na entrega e pelo app. 💳"
    )


def _resposta_reclamacao(tenant):
    return (
        f"Poxa, lamentamos muito pelo ocorrido! 😔\n\n"
        f"Por favor, nos conte mais detalhes para que possamos resolver o mais rápido possível.\n"
        f"Se preferir, acesse nosso site:\n{get_store_link(tenant)}"
    )


def _resposta_fallback(tenant):
    return (
        f"Olá! 😊 No momento só consigo ajudar com pedidos.\n\n"
        f"Para fazer seu pedido acesse:\n"
        f"{get_store_link(tenant)}"
    )


# Mapa de intenção → função de resposta
RESPOSTAS = {
    "saudacao": _resposta_saudacao,
    "pedido": _resposta_pedido,
    "reclamacao": _resposta_reclamacao,
    "fallback": _resposta_fallback,
}


def processar_mensagem_oficial(tenant, config, payload):
    message_type = payload.get('type')
    sender_number = payload.get('from')

    if not sender_number:
        logger.warning("Mensagem recebida sem número de origem.")
        return

    if message_type == 'text':
        text_body = payload.get('text', {}).get('body', '').strip()

        # Classificar intenção
        intencao, confianca = classificar(text_body)
        logger.info(f"[{tenant.slug}] Mensagem: '{text_body}' → Intenção: {intencao} ({confianca:.2f})")

        # Buscar função de resposta ou usar fallback
        fn_resposta = RESPOSTAS.get(intencao, _resposta_fallback)
        resposta = fn_resposta(tenant)

    else:
        logger.info(f"[{tenant.slug}] Mensagem do tipo '{message_type}' recebida — respondendo com fallback.")
        resposta = _resposta_fallback(tenant)

    enviar_mensagem_texto(tenant, sender_number, resposta)
