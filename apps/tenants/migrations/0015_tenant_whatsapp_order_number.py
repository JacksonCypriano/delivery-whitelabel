from django.db import migrations, models

import apps.tenants.utils


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0014_tenant_online_payments_allowed_db_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="whatsapp_order_number",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Opcional. As confirmações dos pedidos serão enviadas para este número. "
                    "Se ficar vazio, serão enviadas para o WhatsApp público da loja."
                ),
                max_length=13,
                validators=[apps.tenants.utils.validate_whatsapp_number],
                verbose_name="WhatsApp para receber pedidos",
            ),
        ),
    ]
