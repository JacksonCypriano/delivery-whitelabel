from django.db import migrations, models


def restore_pending_handoffs(apps, schema_editor):
    Alert = apps.get_model('prospecting', 'CommercialHandoffAlert')
    # Legacy email delivery uncertainty must not conceal unanswered leads.
    Alert.objects.filter(state='email_uncertain', acknowledged_at__isnull=True).update(state='pending')


class Migration(migrations.Migration):
    dependencies = [('prospecting', '0006_commercial_otp_exclusion')]

    operations = [
        migrations.AddField('commercialcontrol', 'handoff_notify_phone', models.CharField(default='5511983491206', max_length=20)),
        migrations.AddField('commercialcontrol', 'handoff_notify_enabled', models.BooleanField(default=False)),
        migrations.AddField('commercialcontrol', 'handoff_notify_enabled_at', models.DateTimeField(blank=True, null=True)),
        migrations.AddField('commercialhandoffalert', 'whatsapp_attempted_at', models.DateTimeField(blank=True, null=True)),
        migrations.AddField('commercialhandoffalert', 'whatsapp_status', models.CharField(default='not_attempted', max_length=20)),
        migrations.AddField('commercialhandoffalert', 'whatsapp_message_id', models.CharField(blank=True, max_length=160)),
        migrations.RunPython(restore_pending_handoffs, migrations.RunPython.noop),
    ]
