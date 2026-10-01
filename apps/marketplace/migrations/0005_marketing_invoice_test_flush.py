# Compatibilidade entre tracking comercial e flush de migrações históricas.
# A relação ORM (incluindo unicidade / on_delete) permanece inalterada;
# apenas as FKs PostgreSQL em billing_invoice são removidas.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0004_marketing_acquisition"),
    ]

    operations = [
        migrations.AlterField(
            model_name="marketingpaidconversion",
            name="invoice",
            field=models.OneToOneField(
                to="billing.invoice",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="marketing_conversion",
                db_constraint=False,
            ),
        ),
        migrations.AlterField(
            model_name="marketingmilestone",
            name="invoice",
            field=models.ForeignKey(
                to="billing.invoice",
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                db_constraint=False,
            ),
        ),
    ]
