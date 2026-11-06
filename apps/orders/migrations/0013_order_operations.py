import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

def backfill_status_updated_at(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.update(status_updated_at=models.F("created_at"))


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0012_order_payment_flow"),
        ("tenants", "0016_tenant_whatsapp_order_number_default"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="customer_phone",
            field=models.CharField(blank=True, max_length=20, verbose_name="Telefone do cliente"),
        ),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pendente"),
                    ("confirmed", "Confirmado"),
                    ("preparing", "Em preparo"),
                    ("ready", "Pronto"),
                    ("out_for_delivery", "Saiu para entrega"),
                    ("delivered", "Entregue"),
                    ("cancelled", "Cancelado"),
                ],
                default="pending",
                max_length=24,
                verbose_name="Situação",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="source",
            field=models.CharField(
                choices=[
                    ("web", "Loja online"),
                    ("whatsapp", "WhatsApp"),
                    ("manual", "Balcão / telefone"),
                ],
                default="web",
                max_length=16,
                verbose_name="Origem do pedido",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="status_updated_at",
            field=models.DateTimeField(
                db_index=True,
                default=django.utils.timezone.now,
                verbose_name="Última mudança de status",
            ),
        ),
        migrations.RunPython(backfill_status_updated_at, noop_reverse),
        migrations.AddField(
            model_name="order",
            name="estimated_ready_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Previsão para ficar pronto",
            ),
        ),
        migrations.CreateModel(
            name="OrderNotificationSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=True, verbose_name="Avisos automáticos de status")),
                ("notify_confirmed", models.BooleanField(default=True, verbose_name="Avisar pedido confirmado")),
                ("notify_preparing", models.BooleanField(default=True, verbose_name="Avisar pedido em preparo")),
                ("notify_ready", models.BooleanField(default=True, verbose_name="Avisar pedido pronto")),
                ("notify_out_for_delivery", models.BooleanField(default=True, verbose_name="Avisar saída para entrega")),
                ("notify_delivered", models.BooleanField(default=True, verbose_name="Avisar pedido entregue")),
                ("notify_cancelled", models.BooleanField(default=True, verbose_name="Avisar cancelamento")),
                ("default_prep_minutes", models.PositiveSmallIntegerField(default=30, verbose_name="Tempo padrão de preparo (minutos)")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="order_notification_settings", to="tenants.tenant", verbose_name="Loja")),
            ],
            options={
                "verbose_name": "Configuração de avisos de pedido",
                "verbose_name_plural": "Configurações de avisos de pedido",
            },
        ),
        migrations.CreateModel(
            name="OrderStatusEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_status", models.CharField(blank=True, choices=[("pending", "Pendente"), ("confirmed", "Confirmado"), ("preparing", "Em preparo"), ("ready", "Pronto"), ("out_for_delivery", "Saiu para entrega"), ("delivered", "Entregue"), ("cancelled", "Cancelado")], max_length=24, verbose_name="Status anterior")),
                ("to_status", models.CharField(choices=[("pending", "Pendente"), ("confirmed", "Confirmado"), ("preparing", "Em preparo"), ("ready", "Pronto"), ("out_for_delivery", "Saiu para entrega"), ("delivered", "Entregue"), ("cancelled", "Cancelado")], max_length=24, verbose_name="Novo status")),
                ("source", models.CharField(choices=[("panel", "Painel do lojista"), ("system", "Sistema"), ("legacy", "Fluxo legado")], default="panel", max_length=16, verbose_name="Origem")),
                ("note", models.CharField(blank=True, max_length=255, verbose_name="Observação")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="order_status_events", to=settings.AUTH_USER_MODEL, verbose_name="Responsável")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_events", to="orders.order", verbose_name="Pedido")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="order_status_events", to="tenants.tenant", verbose_name="Loja")),
            ],
            options={
                "verbose_name": "Evento de status do pedido",
                "verbose_name_plural": "Eventos de status dos pedidos",
                "ordering": ("-created_at", "-pk"),
                "indexes": [models.Index(fields=["tenant", "created_at"], name="order_evt_tenant_time_idx"), models.Index(fields=["order", "created_at"], name="order_evt_order_time_idx")],
            },
        ),
        migrations.CreateModel(
            name="OrderStatusNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recipient", models.CharField(max_length=24, verbose_name="WhatsApp do cliente")),
                ("text", models.TextField(verbose_name="Mensagem")),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("attempted_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("skipped_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=160)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("event", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="notification", to="orders.orderstatusevent", verbose_name="Evento")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="order_status_notifications", to="tenants.tenant", verbose_name="Loja")),
            ],
            options={
                "verbose_name": "Aviso de status do pedido",
                "verbose_name_plural": "Avisos de status dos pedidos",
                "ordering": ("created_at", "pk"),
                "indexes": [models.Index(fields=["sent_at", "skipped_at", "created_at"], name="order_notice_pending_idx")],
            },
        ),
    ]
