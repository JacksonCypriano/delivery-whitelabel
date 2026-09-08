from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("billing", "0013_billingcustomer_billing_address"),
    ]

    operations = [
        migrations.CreateModel(
            name="AsaasFeeSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("environment", models.CharField(choices=[("sandbox", "Ambiente de testes"), ("production", "Produção")], max_length=12, verbose_name="Ambiente")),
                ("fingerprint", models.CharField(db_index=True, max_length=64, verbose_name="Assinatura das taxas")),
                ("payload", models.JSONField(default=dict, verbose_name="Retorno do Asaas")),
                ("pix_fee", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="Pix (R$)")),
                ("boleto_fee", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="Boleto (R$)")),
                ("card_fixed_fee", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="Fixa do cartão (R$)")),
                ("card_1x_percent", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="Cartão 1x (%)")),
                ("card_2_6_percent", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="Cartão 2 a 6x (%)")),
                ("card_7_12_percent", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="Cartão 7 a 12x (%)")),
                ("card_13_21_percent", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="Cartão 13 a 21x (%)")),
                ("nfse_fee", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="NFS-e (R$)")),
                ("child_account_fee", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="Criação de subconta (R$)")),
                ("discount_expires_at", models.DateTimeField(blank=True, null=True, verbose_name="Promoção até")),
                ("observed_at", models.DateTimeField(auto_now_add=True, verbose_name="Consultado em")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True, verbose_name="Revisado em")),
                ("notification_state", models.JSONField(blank=True, default=dict, verbose_name="Alertas enviados")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_asaas_fee_snapshots", to=settings.AUTH_USER_MODEL, verbose_name="Revisado por")),
            ],
            options={
                "verbose_name": "Taxas do Asaas",
                "verbose_name_plural": "Taxas do Asaas",
                "ordering": ["-observed_at"],
                "indexes": [models.Index(fields=["environment", "-observed_at"], name="billing_asa_environ_96d573_idx")],
            },
        ),
    ]
