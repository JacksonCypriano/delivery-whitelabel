from django.db import models
from apps.core.models import TenantModel

class StoreIntelligence(TenantModel):
    """Dados complementares para a IA entender a operação da loja"""
    opening_hours = models.TextField(help_text="Ex: Seg a Sex das 18h às 23h. Sáb e Dom das 18h às 00h.")
    delivery_fee_policy = models.TextField(help_text="Ex: Taxa fixa de R$ 5,00 para todo o bairro. Grátis acima de R$ 50,00.")
    payment_methods = models.TextField(help_text="Ex: Aceitamos Pix, Cartão de Crédito e Débito na entrega.")
    general_faq = models.TextField(blank=True, help_text="Informações gerais extras que a IA deve saber.")

    class Meta:
        verbose_name = "Configuração de IA da Loja"

class KnowledgeChunk(TenantModel):
    """Pedaços de informação que a IA consulta semanticamente"""
    SOURCE_TYPES = [
        ('product', 'Produto'),
        ('category', 'Categoria'),
        ('store_info', 'Info da Loja'),
        ('manual', 'Manual / FAQ'),
        ('global_pattern', 'Padrão Global'),
    ]
    
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    source_id = models.PositiveIntegerField(null=True, blank=True)
    content = models.TextField()
    embedding = models.JSONField(null=True, blank=True) # Vetor numérico
    is_global = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        scope = "Global" if self.is_global else f"Tenant: {self.tenant}"
        return f"[{scope}] {self.source_type}: {self.content[:50]}..."
