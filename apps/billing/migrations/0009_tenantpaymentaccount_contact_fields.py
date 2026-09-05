from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0008_tenantpaymentaccount_terms")]

    operations = [
        migrations.AddField(
            model_name="tenantpaymentaccount",
            name="phone",
            field=models.CharField(blank=True, max_length=20, verbose_name="Telefone fixo"),
        ),
        migrations.AddField(
            model_name="tenantpaymentaccount",
            name="birth_date",
            field=models.DateField(blank=True, null=True, verbose_name="Data de nascimento (CPF)"),
        ),
    ]
