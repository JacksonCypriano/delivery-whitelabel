from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_alter_user_options_alter_user_email_verified_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="must_change_password",
            field=models.BooleanField(
                default=False,
                help_text="Quando ativo, o lojista precisa definir uma nova senha antes de usar o painel.",
                verbose_name="Troca de senha obrigatória",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="welcome_email_sent_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="E-mail de boas-vindas enviado em",
            ),
        ),
    ]
