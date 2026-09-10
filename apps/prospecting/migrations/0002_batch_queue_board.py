import django.db.models.deletion
from django.db import migrations, models


CHUNK_SIZE = 1000


def backfill_batch_contacts(apps, schema_editor):
    ProspectingBatchContact = apps.get_model("prospecting", "ProspectingBatchContact")
    ProspectingQueueItem = apps.get_model("prospecting", "ProspectingQueueItem")

    buffer = []
    for item in ProspectingQueueItem.objects.all().iterator(chunk_size=CHUNK_SIZE):
        buffer.append(
            ProspectingBatchContact(
                batch_id=item.batch_id,
                phone=item.phone,
                establishment=item.establishment,
            )
        )
        if len(buffer) >= CHUNK_SIZE:
            ProspectingBatchContact.objects.bulk_create(
                buffer,
                batch_size=CHUNK_SIZE,
                ignore_conflicts=True,
            )
            buffer = []

    if buffer:
        ProspectingBatchContact.objects.bulk_create(
            buffer,
            batch_size=CHUNK_SIZE,
            ignore_conflicts=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("prospecting", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="prospectingbatch",
            name="contacts_index_complete",
            field=models.BooleanField(
                default=False,
                help_text="Indica que todos os telefones válidos únicos da planilha foram indexados.",
                verbose_name="índice completo da planilha",
            ),
        ),
        migrations.AddField(
            model_name="prospectingbatch",
            name="is_active",
            field=models.BooleanField(db_index=True, default=True, verbose_name="ativa na fila"),
        ),
        migrations.AddField(
            model_name="prospectingbatch",
            name="removed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="removida em"),
        ),
        migrations.CreateModel(
            name="ProspectingBatchContact",
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
                ("phone", models.CharField(db_index=True, max_length=20, verbose_name="telefone")),
                ("establishment", models.CharField(max_length=255, verbose_name="nome da loja")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contacts",
                        to="prospecting.prospectingbatch",
                        verbose_name="planilha",
                    ),
                ),
            ],
            options={
                "verbose_name": "contato de planilha de prospecção",
                "verbose_name_plural": "contatos de planilhas de prospecção",
                "indexes": [
                    models.Index(
                        fields=["batch", "phone"],
                        name="prospect_batch_phone_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("batch", "phone"),
                        name="prospect_batch_contact_unique",
                    )
                ],
            },
        ),
        migrations.RunPython(backfill_batch_contacts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="prospectingqueueitem",
            name="phone",
            field=models.CharField(max_length=20, verbose_name="telefone"),
        ),
        migrations.AddConstraint(
            model_name="prospectingqueueitem",
            constraint=models.UniqueConstraint(
                fields=("batch", "phone"),
                name="prospect_batch_queue_phone_unique",
            ),
        ),
    ]
