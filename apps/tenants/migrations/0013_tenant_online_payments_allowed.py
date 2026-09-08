from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0012_alter_businesshour_tenant_alter_tenant_created_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="online_payments_allowed",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Controle exclusivo do VemDeDelivery. Quando habilitado, o lojista "
                    "poderá solicitar uma subconta Asaas e ativar recebimentos online. "
                    "A criação de subconta pode gerar tarifa no Asaas."
                ),
                verbose_name="Liberar pagamentos online para esta loja",
            ),
        ),
    ]
