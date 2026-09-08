from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_user_initial_access")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="administrative_whatsapp",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Usado para lembretes operacionais do Superadmin, como a conferência mensal do ISS. "
                    "Informe DDD + número; o sistema salva no formato 55DDDNUMERO."
                ),
                max_length=20,
                verbose_name="WhatsApp para alertas administrativos",
            ),
        ),
    ]
