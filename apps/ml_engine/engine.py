import logging
from sentence_transformers import SentenceTransformer
import numpy as np
from django.conf import settings
from apps.stores.models import KnowledgeChunk

logger = logging.getLogger(__name__)

class AISemanticEngine:
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AISemanticEngine, cls).__new__(cls)
        return cls._instance

    @property
    def model(self):
        if self._model is None:
            logger.info("Carregando modelo de IA (SentenceTransformer)...")
            # Modelo leve e eficiente para português/multilíngue
            self._model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        return self._model

    def get_embedding(self, text: str):
        """Transforma texto em um vetor numérico"""
        return self.model.encode(text).tolist()

    def sync_product(self, product):
        """Converte um produto do banco em um KnowledgeChunk"""
        content = (
            f"Produto: {product.name}. "
            f"Preço: R$ {product.price}. "
            f"Descrição: {product.description}. "
            f"Categoria: {product.category.name}."
        )
        
        embedding = self.get_embedding(content)
        
        KnowledgeChunk.objects.update_or_create(
            tenant=product.tenant,
            source_type='product',
            source_id=product.id,
            defaults={
                'content': content,
                'embedding': embedding,
                'is_active': product.is_available
            }
        )
        logger.info(f"Conhecimento sincronizado: {product.name}")

    def search(self, tenant, query_text, limit=3):
        """Busca o conhecimento mais relevante para uma pergunta"""
        query_embedding = self.get_embedding(query_text)
        
        # Busca apenas chunks do tenant ou globais
        chunks = KnowledgeChunk.objects.filter(
            tenant=tenant, 
            is_active=True
        ) | KnowledgeChunk.objects.filter(is_global=True, is_active=True)
        
        results = []
        for chunk in chunks:
            # Cálculo de similaridade de cosseno simples
            sim = np.dot(query_embedding, chunk.embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(chunk.embedding)
            )
            results.append((chunk, sim))
        
        # Ordena pelos mais próximos (maior sim)
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
