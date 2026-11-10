from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('prospecting', '0004_commercialmessage_next_attempt_at'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='CommercialPilotContact',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('phone', models.CharField(max_length=20, unique=True)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='CommercialHandoffAlert',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('reason', models.CharField(max_length=80)),
                ('state', models.CharField(db_index=True, default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('attempted_at', models.DateTimeField(blank=True, null=True)),
                ('acknowledged_at', models.DateTimeField(blank=True, null=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='handoff_alerts', to='prospecting.commercialconversation')),
                ('message', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='handoff_alert', to='prospecting.commercialmessage')),
            ],
        ),
    ]
