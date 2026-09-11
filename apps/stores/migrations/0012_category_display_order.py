from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0011_alter_category_name_alter_category_slug_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="display_order",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Menores valores aparecem primeiro no cardápio.",
                verbose_name="Ordem de exibição",
            ),
        ),
        migrations.AlterModelOptions(
            name="category",
            options={
                "ordering": ["display_order", "name"],
                "verbose_name": "Categoria",
                "verbose_name_plural": "Categorias",
            },
        ),
    ]
