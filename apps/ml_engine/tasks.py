import logging
from celery import shared_task
from apps.stores.models import Product, StoreIntelligence, KnowledgeChunk

logger = logging.getLogger(__name__)


@shared_task(name='ml_engine.sync_ai_knowledge')
def sync_ai_knowledge():
    """
    Task agendada para sincronizar o conhecimento da IA com o banco de dados.
    Roda em background via Celery Beat.
    """
    from apps.ml_engine.engine import AISemanticEngine
    engine = AISemanticEngine()

    total = 0

    # 1. Sincronizar Produtos ativos
    products = Product.objects.filter(is_available=True).select_related('category', 'tenant')
    for product in products:
        try:
            engine.sync_product(product)
            total += 1
        except Exception as e:
            logger.error(f"Erro ao sincronizar produto {product.id}: {e}")

    # 2. Sincronizar Infos da Loja
    infos = StoreIntelligence.objects.select_related('tenant').all()
    for info in infos:
        try:
            content = (
                f"Loja: {info.tenant.name}. "
                f"Horário: {info.opening_hours}. "
                f"Entrega: {info.delivery_fee_policy}. "
                f"Pagamento: {info.payment_methods}. "
                f"Informações extras: {info.general_faq}"
            )
            KnowledgeChunk.objects.update_or_create(
                tenant=info.tenant,
                source_type='store_info',
                source_id=info.id,
                defaults={
                    'content': content,
                    'embedding': engine.get_embedding(content),
                    'is_active': True,
                }
            )
            total += 1
        except Exception as e:
            logger.error(f"Erro ao sincronizar info da loja {info.tenant}: {e}")

    logger.info(f"Sincronização concluída: {total} chunks atualizados.")
    return f"{total} chunks sincronizados."
