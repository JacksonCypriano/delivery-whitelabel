from django.db import models

class ApplyToChoices(models.TextChoices):
    WHOLE = 'whole', 'Inteira'
    HALF = 'half', 'Meia'
    BOTH = 'both', 'Ambas'
