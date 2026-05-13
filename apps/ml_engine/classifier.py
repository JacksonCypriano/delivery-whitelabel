from sentence_transformers import SentenceTransformer
import numpy as np
from typing import Tuple

def classificar(texto: str) -> tuple:
    texto = texto.lower()

    # Reclamação tem prioridade sobre pedido
    if any(palavra in texto for palavra in ["sumiu", "errado", "não recebi", "nao recebi", "demora", "falta", "faltou", "reembolso", "cancelar", "atrasado", "frio", "queimado"]):
        return "reclamacao", 0.9

    elif any(palavra in texto for palavra in ["cardapio", "cardápio", "menu", "quero", "pedir", "fazer pedido", "comprar", "pedido"]):
        return "pedido", 0.9

    elif any(palavra in texto for palavra in ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "e aí", "eai", "salve", "hey"]):
        return "saudacao", 0.9

    else:
        return "fallback", 0.1