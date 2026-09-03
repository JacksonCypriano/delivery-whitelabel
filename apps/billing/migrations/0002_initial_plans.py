from django.db import migrations
from decimal import Decimal


def initialize(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Policy = apps.get_model("billing", "BillingSettings")
    Sub = apps.get_model("billing", "Subscription")
    Tenant = apps.get_model("tenants", "Tenant")
    alias = schema_editor.connection.alias
    Policy.objects.using(alias).get_or_create(pk=1)
    for months, discount, name in [
        (1, 0, "Mensal"),
        (3, 5, "Trimestral"),
        (6, 10, "Semestral"),
        (12, 15, "Anual"),
    ]:
        Plan.objects.using(alias).get_or_create(
            months=months,
            defaults={
                "name": name,
                "monthly_price": Decimal("199"),
                "discount": discount,
            },
        )
    for t in Tenant.objects.using(alias).all().iterator():
        Sub.objects.using(alias).get_or_create(
            tenant_id=t.pk,
            defaults={"managed": False, "manually_blocked": not t.is_active},
        )


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]
    operations = [migrations.RunPython(initialize, migrations.RunPython.noop)]
