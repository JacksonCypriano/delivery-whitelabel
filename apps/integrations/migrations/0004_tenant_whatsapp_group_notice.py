# Generated for VemDeDelivery package 11.7.0

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0003_tenant_whatsapp_conversation_context"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantWhatsAppGroupNotice",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("group_jid", models.CharField(max_length=160, verbose_name="Grupo WhatsApp")),
                ("attempted_at", models.DateTimeField(auto_now_add=True, verbose_name="Primeira tentativa")),
                ("sent_at", models.DateTimeField(blank=True, null=True, verbose_name="Aviso enviado em")),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="whatsapp_group_notices",
                        to="tenants.tenant",
                        verbose_name="Loja",
                    ),
                ),
            ],
            options={
                "verbose_name": "Aviso de grupo do agente WhatsApp",
                "verbose_name_plural": "Avisos de grupo do agente WhatsApp",
            },
        ),
        migrations.AddConstraint(
            model_name="tenantwhatsappgroupnotice",
            constraint=models.UniqueConstraint(
                fields=("tenant", "group_jid"),
                name="unique_whatsapp_group_notice",
            ),
        ),
    ]
