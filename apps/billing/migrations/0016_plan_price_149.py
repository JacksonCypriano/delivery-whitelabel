from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def set_official_plan_price(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(months__in=(1, 3, 6, 12)).update(monthly_price=Decimal("149.00"))


def restore_previous_plan_price(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(months__in=(1, 3, 6, 12)).update(monthly_price=Decimal("199.00"))


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0015_alter_fiscalsettings_nbs_code"),
    ]

    operations = [
        migrations.AlterField(
            model_name="plan",
            name="monthly_price",
            field=models.DecimalField(
                decimal_places=2,
                default=149,
                max_digits=9,
                validators=[django.core.validators.MinValueValidator(Decimal("1"))],
                verbose_name="Valor mensal de referência",
            ),
        ),
        migrations.RunPython(set_official_plan_price, restore_previous_plan_price),
    ]
