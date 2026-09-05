from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("billing", "0005_municipalexport_fiscalinvoice_delivery_at_and_more")]

    operations = [
        migrations.CreateModel(
            name="AdditionalService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(unique=True, verbose_name="Código")),
                ("name", models.CharField(max_length=120, verbose_name="Serviço")),
                ("description", models.CharField(blank=True, max_length=300, verbose_name="Descrição")),
                ("price", models.DecimalField(decimal_places=2, max_digits=9, verbose_name="Valor")),
                ("active", models.BooleanField(default=True, verbose_name="Disponível para contratação")),
            ],
            options={"ordering": ["name"], "verbose_name": "Serviço adicional", "verbose_name_plural": "Serviços adicionais"},
        ),
        migrations.AddField(model_name="invoice", name="additional_service", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="billing.additionalservice", verbose_name="Serviço adicional")),
        migrations.AlterField(model_name="invoice", name="months", field=models.PositiveSmallIntegerField(default=0, verbose_name="Meses comprados")),
        migrations.RunPython(
            lambda apps, schema_editor: [apps.get_model("billing", "AdditionalService").objects.get_or_create(code=code, defaults={"name": name, "description": description, "price": price}) for code, name, description, price in [
                ("cadastro-ate-30-produtos", "Cadastro inicial — até 30 produtos", "Cadastro inicial de até 30 produtos.", "249.00"),
                ("cadastro-ate-60-produtos", "Cadastro inicial — até 60 produtos", "Cadastro inicial de até 60 produtos.", "399.00"),
                ("lote-10-produtos-extras", "Produtos extras — lote de até 10", "Inclusão de até 10 produtos extras.", "69.00"),
                ("atualizacao-20-alteracoes", "Atualização — até 20 alterações simples", "Atualização de até 20 alterações simples.", "59.00"),
            ]],
            migrations.RunPython.noop,
        ),
    ]
