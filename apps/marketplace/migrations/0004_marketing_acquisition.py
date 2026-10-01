from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0003_alter_marketplacecategory_slug_and_more"),
        ("tenants", "0016_tenant_whatsapp_order_number_default"),
        ("billing", "0016_plan_price_149"),
    ]

    operations = [
        migrations.CreateModel(
            name="MarketingLead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference", models.CharField(max_length=20, unique=True, verbose_name="Referência comercial")),
                ("landing_path", models.CharField(blank=True, max_length=220, verbose_name="Página de entrada")),
                ("cta", models.CharField(blank=True, max_length=64, verbose_name="Botão de contato")),
                ("source_note", models.CharField(blank=True, max_length=30, verbose_name="Origem da referência")),
                ("analytics_consent", models.BooleanField(default=False, verbose_name="Consentiu com análise")),
                ("ga_client_id", models.CharField(blank=True, max_length=80, verbose_name="GA4 client ID")),
                *[(field, models.CharField(blank=True, max_length=180)) for field in (
                    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "gbraid", "wbraid")],
                ("qualified_at", models.DateTimeField(blank=True, null=True, verbose_name="Contato qualificado em")),
                ("linked_at", models.DateTimeField(blank=True, null=True, verbose_name="Loja cadastrada/vinculada em")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Clique identificado em")),
                ("tenant", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="marketing_lead", to="tenants.tenant", verbose_name="Loja vinculada")),
            ],
            options={"ordering": ("-created_at",), "verbose_name": "Lead comercial (WhatsApp)", "verbose_name_plural": "Leads comerciais (WhatsApp)"},
        ),
        migrations.CreateModel(
            name="MarketingPaidConversion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Valor pago (BRL)")),
                ("paid_at", models.DateTimeField(verbose_name="Pagamento confirmado em")),
                ("retracted_at", models.DateTimeField(blank=True, null=True, verbose_name="Em revisão/estornado em")),
                ("ga4_sent_at", models.DateTimeField(blank=True, null=True, verbose_name="Enviado ao GA4")),
                ("ga4_last_error", models.CharField(blank=True, max_length=250, verbose_name="Último erro GA4")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("invoice", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="marketing_conversion", to="billing.invoice")),
                ("lead", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="first_payment", to="marketplace.marketinglead")),
            ],
            options={"ordering": ("-paid_at",), "verbose_name": "Primeira assinatura paga (aquisição)", "verbose_name_plural": "Primeiras assinaturas pagas (aquisição)"},
        ),
        migrations.CreateModel(
            name="MarketingMilestone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(choices=[("lead_qualified", "Contato confirmado/qualificado"), ("signup_completed", "Loja cadastrada"), ("subscription_created", "Cobrança inicial criada")], max_length=32, verbose_name="Etapa")),
                ("occurred_at", models.DateTimeField(verbose_name="Data da etapa")),
                ("ga4_sent_at", models.DateTimeField(blank=True, null=True)),
                ("ga4_last_error", models.CharField(blank=True, max_length=250)),
                ("invoice", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="billing.invoice")),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="milestones", to="marketplace.marketinglead")),
            ],
            options={"verbose_name": "Etapa de aquisição", "verbose_name_plural": "Etapas de aquisição"},
        ),
        migrations.AddConstraint(
            model_name="marketingmilestone",
            constraint=models.UniqueConstraint(fields=("lead", "name"), name="uniq_vdd_marketing_milestone"),
        ),
    ]
