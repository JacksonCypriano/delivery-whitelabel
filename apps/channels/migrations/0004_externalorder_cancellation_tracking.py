from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('channels', '0003_externalorder_platform_notes_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='externalorder',
            name='cancellation_state',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
        migrations.AddField(
            model_name='externalorder',
            name='cancellation_requested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='externalorder',
            name='cancellation_error',
            field=models.CharField(blank=True, max_length=240),
        ),
    ]
