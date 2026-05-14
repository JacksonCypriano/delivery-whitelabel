import numpy as np
from sentence_transformers import SentenceTransformer

# Exemplos representativos de cada intenção
# Quanto mais exemplos, melhor a classificação
INTENCOES = {
    "saudacao": [
        "oi", "olá", "ola", "bom dia", "boa tarde", "boa noite",
        "e aí", "eai", "salve", "hey", "tudo bem", "tudo bom",
        "como vai", "oi tudo bem", "olá tudo bem",
    ],
    "pedido": [
        "quero pedir", "fazer um pedido", "quero comprar", "me manda",
        "tem disponível", "vocês têm", "vocês tem", "tem hambúrguer",
        "qual o preço", "quanto custa", "cardápio", "cardapio", "menu",
        "o que tem", "o que vocês vendem", "quero um lanche",
        "tem pizza", "tem açaí", "tem sushi", "tem frango",
        "qual o valor", "me passa o cardápio", "quero ver o menu",
        "tem promoção", "tem combo", "quero pedir comida",
    ],
    "reclamacao": [
        "meu pedido sumiu", "não recebi", "nao recebi", "pedido errado",
        "quero reembolso", "cancelar pedido", "tá atrasado", "demorou demais",
        "comida fria", "comida queimada", "faltou item", "veio faltando",
        "não gostei", "péssimo", "horrível", "reclamação", "problema",
        "insatisfeito", "decepcionado", "errou o pedido",
    ],
    "horario": [
        "que horas abre", "que horas fecha", "horário de funcionamento",
        "vocês estão abertos", "funcionam agora", "aberto agora",
        "qual o horário", "até que horas", "a partir de que horas",
    ],
    "entrega": [
        "fazem entrega", "tem delivery", "entregam aqui", "qual a taxa de entrega",
        "quanto custa a entrega", "tempo de entrega", "quanto tempo demora",
        "entregam no meu bairro", "raio de entrega", "frete",
    ],
    "pagamento": [
        "aceitam pix", "aceitam cartão", "formas de pagamento",
        "pode pagar no cartão", "aceita dinheiro", "aceita débito",
        "como pagar", "pagamento na entrega", "pago como",
    ],
}

# Singleton para não recarregar o modelo a cada chamada
_model = None
_embeddings_cache = {}


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    return _model


def _get_embeddings_cache():
    """Gera e cacheia os embeddings dos exemplos de cada intenção."""
    global _embeddings_cache
    if not _embeddings_cache:
        model = _get_model()
        for intencao, exemplos in INTENCOES.items():
            _embeddings_cache[intencao] = model.encode(exemplos)
    return _embeddings_cache


def classificar(texto: str) -> tuple:
    """
    Classifica a intenção de um texto usando similaridade semântica.
    Retorna (intencao, confianca).
    """
    model = _get_model()
    cache = _get_embeddings_cache()

    # Gera embedding do texto recebido
    texto_embedding = model.encode([texto.lower()])[0]

    melhor_intencao = "fallback"
    melhor_score = 0.0

    for intencao, exemplos_embeddings in cache.items():
        # Calcula similaridade com todos os exemplos da intenção
        scores = np.dot(exemplos_embeddings, texto_embedding) / (
            np.linalg.norm(exemplos_embeddings, axis=1) * np.linalg.norm(texto_embedding)
        )
        # Pega o score mais alto entre os exemplos
        score_max = float(np.max(scores))

        if score_max > melhor_score:
            melhor_score = score_max
            melhor_intencao = intencao

    # Threshold mínimo de confiança
    if melhor_score < 0.40:
        return "fallback", melhor_score

    return melhor_intencao, melhor_score
