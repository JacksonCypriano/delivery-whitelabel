import uuid

from django.conf import settings
from django.db import models


class WhatsAppIntegrationState(models.Model):
    class Status(models.TextChoices):
        UNKNOWN = "unknown", "Ainda não verificado"
        OPEN = "open", "Conectado"
        CLOSED = "close", "Desconectado"
        CONNECTING = "connecting", "Reconectando"
        ERROR = "error", "Erro de comunicação/configuração"
        PAIRING = "pairing", "Necessita novo pareamento"

    identity = models.CharField(
        "Identificação técnica", max_length=64, unique=True, editable=False
    )
    environment = models.CharField("Ambiente", max_length=32)
    instance = models.CharField("Instância", max_length=100)
    status = models.CharField(
        "Situação", max_length=16, choices=Status.choices, default=Status.UNKNOWN
    )
    checked_at = models.DateTimeField("Última verificação concluída", null=True)
    observed_online_at = models.DateTimeField("Última conexão observada", null=True)
    online_since = models.DateTimeField("Conectado continuamente desde", null=True)
    webhook_at = models.DateTimeField("Último webhook recebido", null=True)
    pairing_hint_at = models.DateTimeField("Indício recente de pareamento", null=True)
    webhook_pending = models.BooleanField(default=False, editable=False)
    incident = models.UUIDField("Incidente", null=True, editable=False)
    down_since = models.DateTimeField("Indisponível desde", null=True)
    attempts = models.PositiveSmallIntegerField("Tentativas no incidente", default=0)
    next_attempt_at = models.DateTimeField("Próxima tentativa", null=True)
    manual_required = models.BooleanField(
        "Intervenção manual necessária", default=False
    )
    reason = models.CharField("Diagnóstico", max_length=80, blank=True)
    lease_token = models.UUIDField(null=True, editable=False)
    lease_until = models.DateTimeField(null=True, editable=False)
    manual_requested = models.BooleanField(default=False, editable=False)
    manual_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, editable=False
    )
    action_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        verbose_name = "Conexão WhatsApp / Evolution"
        verbose_name_plural = "Conexões WhatsApp / Evolution"

    def __str__(self):
        return f"{self.environment} — {self.instance}"


class WhatsAppIntegrationEvent(models.Model):
    state = models.ForeignKey(
        WhatsAppIntegrationState,
        on_delete=models.PROTECT,
        related_name="events",
        verbose_name="Conexão",
    )
    created_at = models.DateTimeField("Data", auto_now_add=True)
    kind = models.CharField("Evento", max_length=40)
    description = models.CharField("Descrição", max_length=200)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        verbose_name="Superadministrador",
    )
    incident = models.UUIDField("Incidente", null=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "Evento da integração WhatsApp"
        verbose_name_plural = "Histórico da integração WhatsApp"


class WhatsAppAlert(models.Model):
    class Delivery(models.TextChoices):
        PENDING = "pending", "Pendente"
        SENDING = "sending", "Em envio / resultado ainda não confirmado"
        SENT = "sent", "Aceito pelo servidor de e-mail"
        UNCERTAIN = "uncertain", "Resultado incerto — verificar e-mail"
        SKIPPED = "skipped", "Cancelado por recuperação"

    state = models.ForeignKey(
        WhatsAppIntegrationState, on_delete=models.PROTECT, verbose_name="Conexão"
    )
    incident = models.UUIDField("Incidente", default=uuid.uuid4, editable=False)
    recovery = models.BooleanField("Aviso de recuperação", default=False)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    status = models.CharField(
        "Envio", max_length=16, choices=Delivery.choices, default=Delivery.PENDING
    )
    attempted_at = models.DateTimeField("Tentativa em", null=True)
    sent_at = models.DateTimeField("Aceito em", null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("state", "incident", "recovery"),
                name="unique_whatsapp_incident_alert",
            )
        ]
        verbose_name = "Alerta WhatsApp"
        verbose_name_plural = "Alertas WhatsApp por e-mail"
