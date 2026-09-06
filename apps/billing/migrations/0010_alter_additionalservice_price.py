from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0009_tenantpaymentaccount_contact_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="additionalservice",
            name="price",
            field=models.DecimalField(
                "Valor",
                max_digits=9,
                decimal_places=2,
                validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
            ),
        ),
    ]
