# Generated for VemDeDelivery package 11.1.0

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0002_tenant_whatsapp_agent"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantwhatsappconversation",
            name="context",
            field=models.JSONField(blank=True, default=dict, verbose_name="Contexto curto da conversa"),
        ),
        migrations.AddField(
            model_name="tenantwhatsappconversation",
            name="context_updated_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Contexto atualizado em"),
        ),
    ]
