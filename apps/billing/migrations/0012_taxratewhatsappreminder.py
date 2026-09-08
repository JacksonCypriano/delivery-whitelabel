from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_user_administrative_whatsapp"),
        ("billing", "0011_fiscalsettings_issuer_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaxRateWhatsAppReminder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("month", models.DateField(verbose_name="Competência")),
                ("phone", models.CharField(max_length=20, verbose_name="WhatsApp utilizado")),
                ("status", models.CharField(choices=[("PENDING", "Pendente"), ("SENDING", "Em envio"), ("SENT", "Enviado"), ("FAILED", "Falha; tentar novamente")], default="PENDING", max_length=12, verbose_name="Situação")),
                ("attempts", models.PositiveSmallIntegerField(default=0, verbose_name="Tentativas")),
                ("attempted_at", models.DateTimeField(blank=True, null=True, verbose_name="Última tentativa")),
                ("sent_at", models.DateTimeField(blank=True, null=True, verbose_name="Enviado em")),
                ("last_error", models.CharField(blank=True, max_length=80, verbose_name="Último erro")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Criado em")),
                ("configuration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="billing.fiscalsettings", verbose_name="Configuração fiscal")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="accounts.user", verbose_name="Gestor global")),
            ],
            options={
                "verbose_name": "Lembrete WhatsApp de ISS",
                "verbose_name_plural": "Lembretes WhatsApp de ISS",
                "ordering": ["-month", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="taxratewhatsappreminder",
            constraint=models.UniqueConstraint(fields=("configuration", "month", "recipient"), name="billing_tax_whatsapp_month_recipient_unique"),
        ),
    ]
