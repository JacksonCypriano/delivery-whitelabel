from .utils import enviar_mensagem_via_evolution
from apps.ml_engine.classifier import classificar

def processar_mensagem(payload, tenant):
    numero = payload.get("number")
    texto = payload.get("text", {}).get("body")

    intent = classificar(texto)

    if intent == "pedido":
        resposta = "Vamos montar seu pedido! O que deseja?"
    elif intent == "reclamação":
        resposta = "Sentimos muito. Um atendente entrará em contato."
    else:
        resposta = "Olá! Como posso ajudar?"

    enviar_mensagem_via_evolution(numero, resposta, tenant)
