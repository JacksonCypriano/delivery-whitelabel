from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0007_tenantpaymentaccount_orderpayment")]

    operations = [
        migrations.AddField(
            model_name="tenantpaymentaccount",
            name="terms_accepted",
            field=models.BooleanField(default=False, verbose_name="Concordou com taxas e condições"),
        ),
        migrations.AddField(
            model_name="tenantpaymentaccount",
            name="terms_accepted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Concordância registrada em"),
        ),
    ]
