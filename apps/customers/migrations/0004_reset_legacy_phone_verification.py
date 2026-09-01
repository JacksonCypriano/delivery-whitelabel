from django.db import migrations


def reset_existence_checks(apps, schema_editor):
    # Previous flags meant "number exists", not "owner entered an OTP".
    apps.get_model('customers', 'Customer').objects.using(schema_editor.connection.alias).update(
        phone_verified=False, phone_verified_at=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('customers', '0003_customer_phone_verified_customer_phone_verified_at'),
        ('accounts', '0003_pendingregistration_registrationratelimit_and_more'),
    ]
    operations = [migrations.RunPython(reset_existence_checks, migrations.RunPython.noop)]
