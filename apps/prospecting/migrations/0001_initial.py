from datetime import time

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ProspectingBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("filename", models.CharField(max_length=255, verbose_name="arquivo")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("total_contacts", models.PositiveIntegerField(default=0, verbose_name="contatos na planilha")),
                ("queued_contacts", models.PositiveIntegerField(default=0, verbose_name="novos adicionados")),
                ("skipped_contacted", models.PositiveIntegerField(default=0, verbose_name="já contatados")),
                ("skipped_duplicate", models.PositiveIntegerField(default=0, verbose_name="duplicados/na fila")),
                ("invalid_contacts", models.PositiveIntegerField(default=0, verbose_name="inválidos")),
                ("failed_contacts", models.PositiveIntegerField(default=0, verbose_name="falhas explícitas")),
            ],
            options={
                "verbose_name": "lote de prospecção",
                "verbose_name_plural": "prospecção WhatsApp",
                "ordering": ("-created_at", "-id"),
            },
        ),
        migrations.CreateModel(
            name="ProspectingControl",
            fields=[
                ("singleton_id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("enabled", models.BooleanField(default=False, verbose_name="envios ativos")),
                ("start_time", models.TimeField(default=time(9, 0), verbose_name="horário inicial")),
                ("end_time", models.TimeField(default=time(21, 0), verbose_name="horário final")),
                (
                    "messages_per_minute",
                    models.PositiveSmallIntegerField(
                        default=1,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(10),
                        ],
                        verbose_name="contatos por minuto",
                    ),
                ),
                ("weekdays", models.CharField(default="0,1,2,3,4", max_length=13, verbose_name="dias permitidos")),
            ],
            options={
                "verbose_name": "controle de prospecção",
                "verbose_name_plural": "controle de prospecção",
            },
        ),
        migrations.CreateModel(
            name="ProspectingSentPhone",
            fields=[
                ("phone", models.CharField(max_length=20, primary_key=True, serialize=False, verbose_name="telefone")),
                ("contacted_at", models.DateTimeField(auto_now_add=True, verbose_name="registrado em")),
            ],
            options={
                "verbose_name": "telefone já abordado",
                "verbose_name_plural": "telefones já abordados",
                "ordering": ("-contacted_at", "phone"),
            },
        ),
        migrations.CreateModel(
            name="ProspectingQueueItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(max_length=20, unique=True, verbose_name="telefone")),
                ("establishment", models.CharField(max_length=255, verbose_name="nome da loja")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pendente"),
                            ("PROCESSING", "Processando"),
                            ("SENT", "Enviado"),
                            ("REJECTED", "Rejeitado"),
                            ("UNKNOWN", "Entrega incerta"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=16,
                        verbose_name="situação",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="items",
                        to="prospecting.prospectingbatch",
                        verbose_name="lote",
                    ),
                ),
            ],
            options={
                "verbose_name": "item da fila de prospecção",
                "verbose_name_plural": "itens da fila de prospecção",
                "ordering": ("created_at", "id"),
            },
        ),
        migrations.AddIndex(
            model_name="prospectingqueueitem",
            index=models.Index(fields=["status", "created_at"], name="prospect_status_created_idx"),
        ),
    ]
