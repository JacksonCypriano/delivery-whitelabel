import re
from django.db import migrations, models


def backfill_billing_address(apps, schema_editor):
    BillingCustomer = apps.get_model("billing", "BillingCustomer")
    for customer in BillingCustomer.objects.select_related("tenant").all().iterator():
        tenant = customer.tenant
        postal = re.sub(r"\D", "", tenant.pickup_zip_code or "")
        if len(postal) != 8:
            postal = ""
        updates = {}
        if not customer.postal_code:
            updates["postal_code"] = postal
        if not customer.address:
            updates["address"] = (tenant.pickup_address or "").strip()
        if not customer.address_number:
            updates["address_number"] = (tenant.pickup_number or "").strip()
        if not customer.complement:
            updates["complement"] = (tenant.pickup_complement or "").strip()
        if not customer.province:
            updates["province"] = (tenant.pickup_neighborhood or "").strip()
        if updates:
            BillingCustomer.objects.filter(pk=customer.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [("billing", "0012_taxratewhatsappreminder")]

    operations = [
        migrations.AddField(
            model_name="billingcustomer",
            name="postal_code",
            field=models.CharField(blank=True, max_length=8, verbose_name="CEP de faturamento"),
        ),
        migrations.AddField(
            model_name="billingcustomer",
            name="address",
            field=models.CharField(blank=True, max_length=255, verbose_name="Logradouro de faturamento"),
        ),
        migrations.AddField(
            model_name="billingcustomer",
            name="address_number",
            field=models.CharField(blank=True, max_length=20, verbose_name="Número de faturamento"),
        ),
        migrations.AddField(
            model_name="billingcustomer",
            name="complement",
            field=models.CharField(blank=True, max_length=100, verbose_name="Complemento de faturamento"),
        ),
        migrations.AddField(
            model_name="billingcustomer",
            name="province",
            field=models.CharField(blank=True, max_length=100, verbose_name="Bairro de faturamento"),
        ),
        migrations.RunPython(backfill_billing_address, migrations.RunPython.noop),
    ]
