from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0011_alter_cart_options_alter_cartitem_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="payment_flow",
            field=models.CharField(
                choices=[
                    ("in_person", "Na entrega ou retirada"),
                    ("online", "Online pelo Asaas"),
                ],
                default="in_person",
                max_length=20,
                verbose_name="Tipo de pagamento",
            ),
        ),
    ]
