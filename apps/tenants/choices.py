from django.db import models


class SaleMode(models.TextChoices):
        ONLINE = 'online', 'Venda Online (com pagamento)'
        WHATSAPP = 'whatsapp', 'Apenas WhatsApp (sem pagamento online)'
