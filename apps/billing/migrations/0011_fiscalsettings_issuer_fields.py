from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0010_alter_additionalservice_price")]

    operations = [
        migrations.AddField(
            model_name="fiscalsettings",
            name="fiscal_email",
            field=models.EmailField(blank=True, help_text="E-mail que receberá alertas de NFS-e enviados pelo Asaas.", max_length=254, verbose_name="E-mail fiscal"),
        ),
        migrations.AddField(
            model_name="fiscalsettings",
            name="municipal_inscription",
            field=models.CharField(blank=True, max_length=40, verbose_name="Inscrição municipal / CCM"),
        ),
        migrations.AddField(
            model_name="fiscalsettings",
            name="simples_nacional",
            field=models.BooleanField(default=True, verbose_name="Optante pelo Simples Nacional"),
        ),
        migrations.AddField(
            model_name="fiscalsettings",
            name="cultural_projects_promoter",
            field=models.BooleanField(default=False, verbose_name="Incentivador cultural"),
        ),
        migrations.AddField(
            model_name="fiscalsettings",
            name="cnae",
            field=models.CharField(blank=True, help_text="Somente dígitos, por exemplo 6202300.", max_length=16, verbose_name="CNAE da atividade"),
        ),
        migrations.AddField(
            model_name="fiscalsettings",
            name="special_tax_regime",
            field=models.CharField(default="0", help_text="Código aceito pelo município. Para a configuração atual de São Paulo: 0 = Nenhum.", max_length=8, verbose_name="Regime especial de tributação"),
        ),
        migrations.AddField(
            model_name="fiscalsettings",
            name="national_portal_tax_calculation_regime",
            field=models.CharField(default="1", help_text="Para ME/EPP do Simples: 1 = tributos federais e municipais pelo Simples Nacional.", max_length=8, verbose_name="Regime de apuração no Portal Nacional"),
        ),
        migrations.AddField(
            model_name="fiscalsettings",
            name="nbs_code",
            field=models.CharField(blank=True, help_text="Código NBS sem depender de formatação visual; o Asaas validará o valor.", max_length=32, verbose_name="Código NBS"),
        ),
        migrations.AddField(
            model_name="fiscalsettings",
            name="rps_serie",
            field=models.CharField(default="1", help_text="Série usada pelo emissor. Revise ao migrar para o padrão nacional.", max_length=16, verbose_name="Série do RPS"),
        ),
        migrations.AddField(
            model_name="fiscalsettings",
            name="rps_number",
            field=models.PositiveIntegerField(default=1, help_text="Se nunca houve emissão, use 1; caso contrário informe o próximo número.", validators=[MinValueValidator(1)], verbose_name="Próximo número do RPS"),
        ),
    ]
