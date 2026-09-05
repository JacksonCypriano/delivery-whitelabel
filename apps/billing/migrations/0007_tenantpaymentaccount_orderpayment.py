from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0006_additionalservice_invoice_additional_service"),
        ("orders", "0011_alter_cart_options_alter_cartitem_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantPaymentAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=False, verbose_name="Pagamento online solicitado")),
                ("status", models.CharField(choices=[("REQUESTED", "Solicitação registrada"), ("PENDING", "Aguardando ativação no Asaas"), ("APPROVED", "Aprovada"), ("REJECTED", "Revisar cadastro"), ("ERROR", "Falha de configuração")], default="REQUESTED", max_length=20, verbose_name="Situação")),
                ("legal_name", models.CharField(blank=True, max_length=150, verbose_name="Nome / razão social")),
                ("document", models.CharField(blank=True, max_length=14, verbose_name="CPF / CNPJ")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="E-mail de ativação")),
                ("mobile_phone", models.CharField(blank=True, max_length=20, verbose_name="Celular")),
                ("company_type", models.CharField(blank=True, max_length=20, verbose_name="Tipo de empresa")),
                ("income_value", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="Faturamento / renda mensal")),
                ("address", models.CharField(blank=True, max_length=255, verbose_name="Logradouro")),
                ("address_number", models.CharField(blank=True, max_length=20, verbose_name="Número")),
                ("complement", models.CharField(blank=True, max_length=100, verbose_name="Complemento")),
                ("province", models.CharField(blank=True, max_length=100, verbose_name="Bairro")),
                ("postal_code", models.CharField(blank=True, max_length=9, verbose_name="CEP")),
                ("provider_account_id", models.CharField(blank=True, max_length=80, verbose_name="ID da subconta Asaas")),
                ("wallet_id", models.CharField(blank=True, max_length=80, verbose_name="Wallet ID Asaas")),
                ("encrypted_api_key", models.TextField(blank=True, editable=False, verbose_name="Chave Asaas criptografada")),
                ("activation_url", models.URLField(blank=True, max_length=600, verbose_name="Link de ativação")),
                ("last_error", models.CharField(blank=True, max_length=500, verbose_name="Último erro")),
                ("requested_at", models.DateTimeField(blank=True, null=True, verbose_name="Solicitada em")),
                ("approved_at", models.DateTimeField(blank=True, null=True, verbose_name="Aprovada em")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Criada em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Atualizada em")),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="payment_account", to="tenants.tenant", verbose_name="Loja")),
            ],
            options={"verbose_name": "Conta de pagamentos online", "verbose_name_plural": "Contas de pagamentos online"},
        ),
        migrations.CreateModel(
            name="OrderPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider_account_id", models.CharField(max_length=80, verbose_name="Subconta Asaas")),
                ("checkout_id", models.CharField(blank=True, max_length=100, unique=True, verbose_name="Checkout Asaas")),
                ("checkout_url", models.URLField(blank=True, max_length=600, verbose_name="Link de pagamento")),
                ("external_reference", models.CharField(max_length=120, unique=True, verbose_name="Referência externa")),
                ("confirmation_code", models.CharField(max_length=24, unique=True, verbose_name="Código de confirmação")),
                ("method", models.CharField(max_length=20, verbose_name="Forma de pagamento")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Valor")),
                ("status", models.CharField(choices=[("PENDING", "Aguardando pagamento"), ("PAID", "Pagamento confirmado"), ("CANCELED", "Cancelado"), ("EXPIRED", "Expirado"), ("ERROR", "Falha no pagamento")], default="PENDING", max_length=12, verbose_name="Situação")),
                ("paid_at", models.DateTimeField(blank=True, null=True, verbose_name="Confirmado em")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Atualizado em")),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="online_payment", to="orders.order", verbose_name="Pedido")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant", verbose_name="Loja")),
            ],
            options={"verbose_name": "Pagamento de pedido", "verbose_name_plural": "Pagamentos de pedidos", "ordering": ["-created_at"]},
        ),
    ]
