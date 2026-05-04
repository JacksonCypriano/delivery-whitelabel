from sentence_transformers import SentenceTransformer
import numpy as np

MODEL = SentenceTransformer('all-MiniLM-L6-v2')

INTENTS = {
    "saudacao": ["oi", "ola", "bom dia", "boa tarde"],
    "pedido": ["quero pedir", "gostaria de", "pode me vender", "fazer pedido"],
    "reclamação": ["meu pedido sumiu", "veio errado", "não recebi", "demora demais"]
}

EMBEDDINGS = {k: MODEL.encode(v) for k, v in INTENTS.items()}

def classificar(texto):
    emb = MODEL.encode([texto])
    scores = {}
    for intent, vectors in EMBEDDINGS.items():
        scores[intent] = np.dot(emb, vectors)[0].mean()
    return max(scores, key=scores.get)