import re
from django.core.exceptions import ValidationError

def validate_whatsapp_number(value: str):
        clean = re.sub(r'\D', '', value)

        if not re.match(r'^55\d{10,11}$', clean):
            raise ValidationError(
                "Número inválido. Use formato: 5511999999999"
            )

        ddd = clean[2:4]
        numero = clean[4:]

        if len(numero) == 9 and not numero.startswith('9'):
            raise ValidationError("Celular inválido (deve começar com 9).")

        return clean
