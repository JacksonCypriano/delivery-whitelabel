from django.db import models


class SaleMode(models.TextChoices):
        ONLINE = 'online', 'Venda Online (com pagamento)'
        WHATSAPP = 'whatsapp', 'Apenas WhatsApp (sem pagamento online)'

class FulfillmentMode(models.TextChoices):
    DELIVERY_AND_PICKUP = "delivery_and_pickup", "Entrega e Retirada"
    PICKUP_ONLY = "pickup_only", "Apenas Retirada"
    DELIVERY_ONLY = "delivery_only", "Apenas entrega"
