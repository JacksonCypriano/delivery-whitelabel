from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('prospecting', '0003_commercialcontrol_commercialconversation_and_more')]
    operations = [migrations.AddField(
        model_name='commercialmessage',
        name='next_attempt_at',
        field=models.DateTimeField(blank=True, null=True, db_index=True),
    )]
