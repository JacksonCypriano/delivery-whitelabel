from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('prospecting', '0005_commercial_pilot_safety')]

    operations = [
        migrations.CreateModel(
            name='CommercialOtpExclusion',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('instance', models.CharField(max_length=100)),
                ('phone', models.CharField(max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_otp_at', models.DateTimeField(auto_now=True)),
            ],
            options={'constraints': [models.UniqueConstraint(fields=('instance', 'phone'), name='commercial_otp_exclusion_unique')]},
        ),
    ]
