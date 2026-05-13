from django.db import models
from apps.tenants.models import Tenant

class AIConsultation(models.Model):
    """Registro de cada consulta feita ao motor de IA"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    customer_phone = models.CharField(max_length=20)
    user_message = models.TextField()
    ai_response = models.TextField()
    detected_intent = models.CharField(max_length=50, blank=True)
    confidence_score = models.FloatField(default=0.0)
    
    # Feedback para aprendizado
    was_helpful = models.BooleanField(null=True, blank=True)
    human_correction = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

class TrainingExample(models.Model):
    """Exemplos de perguntas e respostas para aprendizado entre tenants"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    is_global = models.BooleanField(default=False)
    
    question = models.TextField()
    ideal_response = models.TextField()
    intent_label = models.CharField(max_length=50)
    
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Q: {self.question[:30]} -> {self.intent_label}"
