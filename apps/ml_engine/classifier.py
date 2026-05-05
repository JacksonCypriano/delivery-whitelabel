from sentence_transformers import SentenceTransformer
import numpy as np
from typing import Tuple

# # Lazy globals
# _MODEL = None
# _EMBEDDINGS = None
# _INTENTS = None

# def get_model() -> SentenceTransformer:
#     global _MODEL
#     if _MODEL is None:
#         _MODEL = SentenceTransformer('all-MiniLM-L6-v2')
#     return _MODEL

# def get_intents() -> dict:
#     global _INTENTS
#     if _INTENTS is None:
#         _INTENTS = {
#             "saudacao": [
#                 "oi",
#                 "olá",
#                 "ola",
#                 "oii",
#                 "oie",
#                 "bom dia",
#                 "boa tarde",
#                 "boa noite",
#                 "e aí",
#                 "e ai",
#                 "tudo bem?",
#                 "tudo bem",
#                 "tudo certo?",
#                 "ola tudo bem",
#                 "oi tudo bem",
#                 "salve",
#                 "boa tarde, tudo bem?",
#                 "bom dia, gostaria de informação",
#                 "hey",
#                 "oi pessoal",
#                 "olá pessoal",
#                 "bom dia equipe"
#             ],

#             "pedido": [
#                 "quero pedir",
#                 "gostaria de pedir",
#                 "posso fazer um pedido?",
#                 "vou querer",
#                 "quero fazer um pedido",
#                 "fazer pedido",
#                 "pedido para entrega",
#                 "pedido pra entrega",
#                 "para retirada",
#                 "vou retirar",
#                 "retirar no balcão",
#                 "quero pedir um hambúrguer",
#                 "quero pedir uma pizza",
#                 "peça para entrega",
#                 "tem como agendar a entrega?",
#                 "posso agendar para mais tarde?",
#                 "tem promoção hoje?",
#                 "tem cupom de desconto?",
#                 "qual o preço do X?",
#                 "quanto custa o combo?",
#                 "adicionar batata",
#                 "sem cebola por favor",
#                 "sem picles",
#                 "com maionese",
#                 "trocar o pão por integral",
#                 "queria alterar meu pedido",
#                 "posso trocar um item do pedido?",
#                 "alterar meu pedido",
#                 "cancelar pedido",
#                 "como faço para pagar?",
#                 "aceita cartão?",
#                 "aceita cartão no app?",
#                 "valor do frete",
#                 "tempo de entrega",
#                 "quanto tempo para entrega?",
#                 "tem opção vegetariana?",
#                 "tem opção sem glúten?",
#                 "criar pedido via whatsapp",
#                 "pedido delivery",
#                 "pedido para retirada no local",
#                 "fazer pedido agora",
#                 "quero mais informações sobre o cardápio",
#                 "mostrar cardápio",
#                 "ver cardápio",
#                 "tem promoçao",
#                 "tem promoção para hoje",
#                 "me passa o preço do X",
#                 "quero 2 unidades do Classic Cheese",
#                 "colocar sem sal",
#                 "colocar molho separado",
#                 "incluir observação no pedido",
#                 "posso pagar na entrega (money/efetivo)?",
#                 "tem taxa extra para cartão?"
#             ],

#             "reclamacao": [
#                 "meu pedido sumiu",
#                 "não recebi meu pedido",
#                 "nao recebi meu pedido",
#                 "veio errado",
#                 "pedido veio errado",
#                 "faltou item",
#                 "faltou um item no pedido",
#                 "faltou batata",
#                 "faltou refrigerante",
#                 "pedido incompleto",
#                 "comida fria",
#                 "chegou fria",
#                 "comida estragada",
#                 "mau cheiro",
#                 "pedido queimado",
#                 "produto vencido",
#                 "erro na cobrança",
#                 "fui cobrado a mais",
#                 "cobrança indevida",
#                 "está demorando demais",
#                 "demora demais",
#                 "motorista sumiu",
#                 "entregador não apareceu",
#                 "entregador nao apareceu",
#                 "entrega atrasada",
#                 "quero reembolso",
#                 "quero devolver",
#                 "quero falar com o gerente",
#                 "preciso de suporte",
#                 "reclamar sobre o pedido",
#                 "pedido veio com defeito",
#                 "alergia foi ignorada",
#                 "contém alergênicos não informados",
#                 "faltou tempero",
#                 "sabor ruim",
#                 "qualidade ruim",
#                 "nao esta como anunciado",
#                 "não corresponde ao que pedi",
#                 "não aceito esse pedido",
#                 "quero cancelamento e estorno",
#                 "solicito reembolso",
#                 "não fui avisado do atraso",
#                 "veio com embalagem danificada",
#                 "fiz pedido e foi cancelado sem aviso",
#                 "erro no troco",
#                 "troco errado"
#             ]
#         }
#         }
#     return _INTENTS

# def get_embeddings() -> dict:
#     global _EMBEDDINGS
#     if _EMBEDDINGS is None:
#         model = get_model()
#         intents = get_intents()
#         raw = {k: model.encode(v) for k, v in intents.items()}
#         _EMBEDDINGS = {}
#         for k, arr in raw.items():
#             norms = np.linalg.norm(arr, axis=1, keepdims=True)
#             norms[norms == 0] = 1.0
#             _EMBEDDINGS[k] = arr / norms
#     return _EMBEDDINGS

# def classificar(texto: str) -> Tuple[str, float]:
#     model = get_model()
#     embeddings = get_embeddings()

#     emb = model.encode([texto])
#     emb_norm = emb / np.linalg.norm(emb, axis=1, keepdims=True)

#     scores = {}
#     for intent, vectors in embeddings.items():
#         sims = np.dot(emb_norm, vectors.T)[0]
#         scores[intent] = float(np.mean(sims))

#     best_intent = max(scores, key=scores.get)
#     return best_intent, scores[best_intent]

def classificar(texto: str) -> tuple:
    texto = texto.lower()

    if any(palavra in texto for palavra in ["pedido", "quero", "fazer pedido", "comprar"]):
        return "pedido", 0.9
    elif any(palavra in texto for palavra in ["oi", "olá", "bom dia", "boa tarde", "e aí", "ola"]):
        return "saudacao", 0.9
    elif any(palavra in texto for palavra in ["sumiu", "errado", "não recebi", "demora", "falta"]):
        return "reclamacao", 0.9
    else:
        return "fallback", 0.1