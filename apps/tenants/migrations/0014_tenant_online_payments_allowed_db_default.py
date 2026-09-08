from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0013_tenant_online_payments_allowed"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenant",
            name="online_payments_allowed",
            field=models.BooleanField(
                default=False,
                db_default=False,
                help_text=(
                    "Controle exclusivo do VemDeDelivery. Quando habilitado, o lojista "
                    "poderá solicitar uma subconta Asaas e ativar recebimentos online. "
                    "A criação de subconta pode gerar tarifa no Asaas."
                ),
                verbose_name="Liberar pagamentos online para esta loja",
            ),
        ),
    ]
