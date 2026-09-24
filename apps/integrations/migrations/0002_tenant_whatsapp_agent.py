# Generated for VemDeDelivery package 11.0.0

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0001_initial"),
        ("tenants", "0014_tenant_online_payments_allowed_db_default"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantWhatsAppAgent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("instance_name", models.CharField(editable=False, max_length=100, unique=True, verbose_name="Instância Evolution")),
                ("status", models.CharField(choices=[("unknown", "Ainda não verificado"), ("open", "Conectado"), ("close", "Desconectado"), ("connecting", "Reconectando"), ("pairing", "Aguardando pareamento"), ("error", "Erro")], default="unknown", max_length=16, verbose_name="Situação")),
                ("ai_enabled", models.BooleanField(default=False, verbose_name="Agente de atendimento ativo")),
                ("instance_created", models.BooleanField(default=False, editable=False, verbose_name="Instância criada na Evolution")),
                ("requires_pairing", models.BooleanField(default=False, editable=False, verbose_name="Necessita novo pareamento")),
                ("reconnect_attempts", models.PositiveSmallIntegerField(default=0, editable=False, verbose_name="Tentativas de reconexão")),
                ("next_reconnect_at", models.DateTimeField(blank=True, editable=False, null=True, verbose_name="Próxima tentativa de reconexão")),
                ("checked_at", models.DateTimeField(blank=True, editable=False, null=True, verbose_name="Última verificação")),
                ("webhook_at", models.DateTimeField(blank=True, editable=False, null=True, verbose_name="Último webhook")),
                ("connected_at", models.DateTimeField(blank=True, editable=False, null=True, verbose_name="Última conexão")),
                ("disconnected_at", models.DateTimeField(blank=True, editable=False, null=True, verbose_name="Última desconexão")),
                ("last_error", models.CharField(blank=True, editable=False, max_length=160, verbose_name="Diagnóstico")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="whatsapp_agent", to="tenants.tenant", verbose_name="Loja")),
            ],
            options={"verbose_name": "Agente WhatsApp da loja", "verbose_name_plural": "Agentes WhatsApp das lojas"},
        ),
        migrations.CreateModel(
            name="TenantWhatsAppAgentEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Data")),
                ("kind", models.CharField(max_length=40, verbose_name="Evento")),
                ("description", models.CharField(max_length=200, verbose_name="Descrição")),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="integrations.tenantwhatsappagent", verbose_name="Agente")),
            ],
            options={"verbose_name": "Evento do agente WhatsApp", "verbose_name_plural": "Eventos dos agentes WhatsApp", "ordering": ("-created_at", "-pk")},
        ),
        migrations.CreateModel(
            name="TenantWhatsAppConversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone_number", models.CharField(max_length=24, verbose_name="WhatsApp do cliente")),
                ("ai_paused_until", models.DateTimeField(blank=True, null=True, verbose_name="Agente pausado até")),
                ("pause_reason", models.CharField(blank=True, choices=[("order", "Pedido enviado"), ("manual", "Atendimento manual da loja"), ("human", "Cliente pediu atendimento humano")], max_length=16, verbose_name="Motivo da pausa")),
                ("last_customer_message_at", models.DateTimeField(blank=True, null=True, verbose_name="Última mensagem do cliente")),
                ("last_agent_message_at", models.DateTimeField(blank=True, null=True, verbose_name="Última resposta do agente")),
                ("last_store_message_at", models.DateTimeField(blank=True, null=True, verbose_name="Última mensagem manual da loja")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="whatsapp_conversations", to="tenants.tenant", verbose_name="Loja")),
            ],
            options={"verbose_name": "Conversa do agente WhatsApp", "verbose_name_plural": "Conversas do agente WhatsApp"},
        ),
        migrations.AddIndex(model_name="tenantwhatsappagent", index=models.Index(fields=["status", "ai_enabled"], name="wa_agent_status_ai_idx")),
        migrations.AddConstraint(model_name="tenantwhatsappconversation", constraint=models.UniqueConstraint(fields=("tenant", "phone_number"), name="unique_whatsapp_agent_conversation")),
        migrations.AddIndex(model_name="tenantwhatsappconversation", index=models.Index(fields=["tenant", "ai_paused_until"], name="wa_conv_tenant_pause_idx")),
    ]
