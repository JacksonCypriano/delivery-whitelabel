from django.db import models


class Status(models.TextChoices):
    # Keep the historical DB values for backwards compatibility. The React
    # operations board presents ``pending`` as "Novo" without rewriting old
    # orders or external integrations that already know these values.
    PENDING = "pending", "Pendente"
    CONFIRMED = "confirmed", "Confirmado"
    PREPARING = "preparing", "Em preparo"
    READY = "ready", "Pronto"
    READY_FOR_PICKUP = "ready_for_pickup", "Pronto para retirada"
    OUT_FOR_DELIVERY = "out_for_delivery", "Saiu para entrega"
    DELIVERED = "delivered", "Entregue"
    CANCELLED = "cancelled", "Cancelado"


class OrderSource(models.TextChoices):
    WEB = "web", "Loja online"
    WHATSAPP = "whatsapp", "WhatsApp"
    MANUAL = "manual", "Balcão / telefone"


class StatusEventSource(models.TextChoices):
    PANEL = "panel", "Painel do lojista"
    SYSTEM = "system", "Sistema"
    LEGACY = "legacy", "Fluxo legado"
