from decimal import Decimal
import re
from zoneinfo import ZoneInfo
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


def fiscal_today():
    return timezone.localdate(timezone=ZoneInfo("America/Sao_Paulo"))


class FiscalSettings(models.Model):
    environment = models.CharField(
        "Ambiente",
        max_length=12,
        unique=True,
        choices=[("sandbox", "Ambiente de testes"), ("production", "Produção")],
    )
    enabled = models.BooleanField("Emissão automática habilitada", default=False)
    start_at = models.DateTimeField(
        "Considerar pagamentos confirmados a partir de",
        null=True,
        blank=True,
        help_text="Defina o início da implantação. Não emite notas antigas automaticamente.",
    )
    service_id = models.CharField(
        "ID do serviço municipal no Asaas", max_length=80, blank=True
    )
    service_code = models.CharField(
        "Código do serviço aceito pelo Asaas",
        max_length=40,
        blank=True,
        help_text="Informe o ID acima OU este código, conforme a configuração municipal/nacional da conta Asaas. Não confunda com CNAE.",
    )
    service_name = models.CharField(
        "Nome do serviço",
        max_length=200,
        default="Licenciamento da plataforma VemDeDelivery",
    )
    description = models.CharField(
        "Descrição da assinatura",
        max_length=500,
        default="Licenciamento de uso da plataforma VemDeDelivery",
    )

    # Dados não sigilosos da conta emissora no Asaas. O certificado A1 e sua
    # senha nunca são persistidos no banco; são informados apenas ao comando
    # explícito de sincronização fiscal.
    fiscal_email = models.EmailField(
        "E-mail fiscal",
        blank=True,
        help_text="E-mail que receberá alertas de NFS-e enviados pelo Asaas.",
    )
    municipal_inscription = models.CharField(
        "Inscrição municipal / CCM", max_length=40, blank=True
    )
    simples_nacional = models.BooleanField("Optante pelo Simples Nacional", default=True)
    cultural_projects_promoter = models.BooleanField(
        "Incentivador cultural", default=False
    )
    cnae = models.CharField(
        "CNAE da atividade",
        max_length=16,
        blank=True,
        help_text="Somente dígitos, por exemplo 6202300.",
    )
    special_tax_regime = models.CharField(
        "Regime especial de tributação",
        max_length=8,
        default="0",
        help_text="Código aceito pelo município. Para a configuração atual de São Paulo: 0 = Nenhum.",
    )
    national_portal_tax_calculation_regime = models.CharField(
        "Regime de apuração no Portal Nacional",
        max_length=8,
        default="1",
        help_text="Para ME/EPP do Simples: 1 = tributos federais e municipais pelo Simples Nacional.",
    )
    nbs_code = models.CharField(
        "Código NBS",
        max_length=32,
        blank=True,
        help_text=(
            "Use o formato oficial aceito pelo Asaas, por exemplo 1.1103.22.00. "
            "Se informar somente os 9 dígitos, o VemDeDelivery aplica a máscara automaticamente."
        ),
    )
    rps_serie = models.CharField(
        "Série do RPS",
        max_length=16,
        default="1",
        help_text="Série usada pelo emissor. Revise ao migrar para o padrão nacional.",
    )
    rps_number = models.PositiveIntegerField(
        "Próximo número do RPS",
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Se nunca houve emissão, use 1; caso contrário informe o próximo número.",
    )

    class Meta:
        verbose_name = "Configuração de NFS-e"
        verbose_name_plural = "Configurações de NFS-e"

    def __str__(self):
        return self.get_environment_display()

    def clean(self):
        if self.municipal_inscription:
            digits = re.sub(r"\D", "", self.municipal_inscription)
            if len(digits) != 8:
                raise ValidationError(
                    {
                        "municipal_inscription": (
                            "O CCM da Prefeitura de São Paulo deve conter 8 dígitos. "
                            "Exemplo: 1.673.942-6."
                        )
                    }
                )
            self.municipal_inscription = (
                f"{digits[0]}.{digits[1:4]}.{digits[4:7]}-{digits[7]}"
            )

        if self.nbs_code:
            nbs_digits = re.sub(r"\D", "", self.nbs_code)
            if len(nbs_digits) != 9:
                raise ValidationError(
                    {
                        "nbs_code": (
                            "O NBS deve conter 9 dígitos no formato oficial, por exemplo "
                            "1.1103.22.00."
                        )
                    }
                )
            self.nbs_code = (
                f"{nbs_digits[0]}.{nbs_digits[1:5]}."
                f"{nbs_digits[5:7]}.{nbs_digits[7:9]}"
            )

        if self.enabled and (
            not self.start_at or bool(self.service_id) == bool(self.service_code)
        ):
            raise ValidationError(
                "Para habilitar, informe o início e exatamente um identificador: ID ou código do serviço."
            )

    def fiscal_account_missing_fields(self):
        required = {
            "fiscal_email": self.fiscal_email,
            "municipal_inscription": self.municipal_inscription,
            "cnae": self.cnae,
            "special_tax_regime": self.special_tax_regime,
            "nbs_code": self.nbs_code,
            "rps_serie": self.rps_serie,
            "rps_number": self.rps_number,
        }
        if self.simples_nacional:
            required[
                "national_portal_tax_calculation_regime"
            ] = self.national_portal_tax_calculation_regime
        return [name for name, value in required.items() if value in (None, "")]

    def fiscal_account_payload(self):
        missing = self.fiscal_account_missing_fields()
        if missing:
            raise ValidationError(
                "Configuração fiscal incompleta: " + ", ".join(missing)
            )
        data = {
            "email": self.fiscal_email,
            # O Superadmin mantém o CCM formatado para leitura humana, mas a API
            # fiscal do Asaas/prefeitura recebe somente os 8 dígitos.
            "municipalInscription": re.sub(r"\D", "", self.municipal_inscription),
            "simplesNacional": self.simples_nacional,
            "culturalProjectsPromoter": self.cultural_projects_promoter,
            "cnae": self.cnae,
            "specialTaxRegime": self.special_tax_regime,
            "nbsCode": self.nbs_code,
            "rpsSerie": self.rps_serie,
            "rpsNumber": self.rps_number,
        }
        if self.simples_nacional and self.national_portal_tax_calculation_regime:
            data[
                "nationalPortalTaxCalculationRegime"
            ] = self.national_portal_tax_calculation_regime
        return data


class TaxRate(models.Model):
    configuration = models.ForeignKey(
        FiscalSettings, on_delete=models.PROTECT, verbose_name="Configuração fiscal"
    )
    month = models.DateField("Competência (primeiro dia do mês)")
    iss = models.DecimalField(
        "Alíquota de ISS (%)",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("5"))],
        help_text="ATENÇÃO: confira no INÍCIO DE CADA MÊS em Contabilizei → Minhas Rotinas → Ver minhas alíquotas. O ISS varia com o faturamento; não use aqui a alíquota total do Simples. Cadastre também quando o percentual permanecer igual.",
    )
    checked_at = models.DateTimeField(
        "Última conferência registrada", null=True, editable=False
    )
    checked_by = models.ForeignKey(
        "accounts.User",
        null=True,
        editable=False,
        on_delete=models.SET_NULL,
        verbose_name="Conferida por",
    )

    class Meta:
        verbose_name = "Alíquota mensal de ISS"
        verbose_name_plural = "Alíquotas mensais de ISS"
        constraints = [
            models.UniqueConstraint(
                fields=["configuration", "month"], name="billing_tax_month_unique"
            )
        ]

    def __str__(self):
        return f"{self.configuration} · {self.month:%m/%Y} · {self.iss}%"

    def clean(self):
        if self.month and (self.month.day != 1 or self.month > fiscal_today()):
            raise ValidationError(
                "Use o primeiro dia de uma competência atual ou passada; não antecipe a conferência de meses futuros."
            )


class TaxRateWhatsAppReminder(models.Model):
    STATUS = [
        ("PENDING", "Pendente"),
        ("SENDING", "Em envio"),
        ("SENT", "Enviado"),
        ("FAILED", "Falha; tentar novamente"),
    ]

    configuration = models.ForeignKey(
        FiscalSettings,
        on_delete=models.PROTECT,
        verbose_name="Configuração fiscal",
    )
    month = models.DateField("Competência")
    recipient = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        verbose_name="Gestor global",
    )
    phone = models.CharField("WhatsApp utilizado", max_length=20)
    status = models.CharField(
        "Situação", max_length=12, choices=STATUS, default="PENDING"
    )
    attempts = models.PositiveSmallIntegerField("Tentativas", default=0)
    attempted_at = models.DateTimeField("Última tentativa", null=True, blank=True)
    sent_at = models.DateTimeField("Enviado em", null=True, blank=True)
    last_error = models.CharField("Último erro", max_length=80, blank=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Lembrete WhatsApp de ISS"
        verbose_name_plural = "Lembretes WhatsApp de ISS"
        ordering = ["-month", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["configuration", "month", "recipient"],
                name="billing_tax_whatsapp_month_recipient_unique",
            )
        ]

    def __str__(self):
        return f"{self.month:%m/%Y} · {self.recipient} · {self.get_status_display()}"


class FiscalInvoice(models.Model):
    pdf_content = models.BinaryField("PDF arquivado", null=True, editable=False)
    xml_content = models.BinaryField("XML arquivado", null=True, editable=False)
    pdf_sha256 = models.CharField(
        "SHA-256 do PDF", max_length=64, blank=True, editable=False
    )
    xml_sha256 = models.CharField(
        "SHA-256 do XML", max_length=64, blank=True, editable=False
    )
    delivery_status = models.CharField(
        "Envio por e-mail",
        max_length=12,
        default="PENDING",
        choices=[
            ("PENDING", "Pendente"),
            ("SENDING", "Em envio / verificar se interrompido"),
            ("SENT", "Aceito pelo servidor de e-mail"),
            ("UNCERTAIN", "Resultado incerto — revisão manual"),
        ],
    )
    delivery_email = models.EmailField(
        "Destinatário da nota", blank=True, editable=False
    )
    delivery_at = models.DateTimeField(
        "Aceito pelo servidor em", null=True, editable=False
    )
    delivery_checked_at = models.DateTimeField(
        "Última tentativa de arquivamento/envio", null=True, editable=False
    )
    delivery_notice = models.CharField(
        "Aviso de documentos/e-mail", max_length=400, blank=True, editable=False
    )
    STATES = [
        ("PENDING", "Pendente"),
        ("UNCERTAIN", "Solicitação em conciliação"),
        ("SCHEDULED", "Agendada"),
        ("SYNCHRONIZED", "Enviada à prefeitura"),
        ("AUTHORIZED", "Autorizada"),
        ("ERROR", "Erro — revisar no Asaas"),
        ("CANCELED", "Cancelada"),
        ("PROCESSING_CANCELLATION", "Cancelamento em processamento"),
        ("CANCELLATION_DENIED", "Cancelamento negado"),
    ]
    invoice = models.OneToOneField(
        "billing.Invoice",
        on_delete=models.PROTECT,
        related_name="fiscal_note",
        verbose_name="Cobrança",
    )
    provider_id = models.CharField(
        "ID da NFS-e no Asaas", max_length=80, null=True, blank=True, unique=True
    )
    status = models.CharField(
        "Situação", max_length=30, choices=STATES, default="PENDING"
    )
    effective_date = models.DateField(
        "Data de emissão / competência", null=True, blank=True
    )
    amount = models.DecimalField(
        "Valor integral contratado", max_digits=12, decimal_places=2
    )
    iss = models.DecimalField(
        "ISS utilizado (%)", max_digits=5, decimal_places=2, null=True, blank=True
    )
    payload = models.JSONField(
        "Dados fiscais enviados (registro histórico)", default=dict
    )
    attempted = models.BooleanField("Solicitação já enviada", default=False)
    review_required = models.BooleanField("Exige revisão fiscal", default=False)
    notice = models.CharField("Aviso operacional", max_length=400, blank=True)
    number = models.CharField("Número da nota", max_length=80, blank=True)
    pdf_url = models.URLField("PDF no provedor", max_length=2000, blank=True)
    xml_url = models.URLField(
        "XML no provedor, quando disponível", max_length=2000, blank=True
    )
    last_checked_at = models.DateTimeField("Última conciliação", null=True, blank=True)
    created_at = models.DateTimeField("Criada em", auto_now_add=True)

    class Meta:
        verbose_name = "Nota fiscal de assinatura"
        verbose_name_plural = "Notas fiscais de assinaturas"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.invoice.tenant} · {self.get_status_display()}"

    @property
    def reference(self):
        return f"vdd-nfse:{self.invoice.environment}:{self.invoice_id}"


class FiscalCustomerRule(models.Model):
    customer = models.OneToOneField(
        "billing.BillingCustomer",
        on_delete=models.PROTECT,
        verbose_name="Pagador (loja e ambiente)",
    )
    retain_iss = models.BooleanField("Reter ISS", default=False)
    hold = models.BooleanField("Pausar emissão para revisão fiscal", default=True)
    reason = models.CharField("Orientação contábil / motivo", max_length=400)

    class Meta:
        verbose_name = "Exceção fiscal do pagador"
        verbose_name_plural = "Exceções fiscais dos pagadores"

    def __str__(self):
        return str(self.customer)


class MunicipalExport(models.Model):
    month = models.DateField("Competência (primeiro dia do mês)")
    environment = models.CharField(
        "Ambiente",
        max_length=12,
        choices=[("sandbox", "Ambiente de testes"), ("production", "Produção")],
    )
    filename = models.CharField(
        "Nome do arquivo original", max_length=200, editable=False
    )
    content = models.BinaryField("CSV original da prefeitura", editable=False)
    sha256 = models.CharField("SHA-256", max_length=64, editable=False)
    uploaded_at = models.DateTimeField("Arquivado em", auto_now_add=True)

    class Meta:
        verbose_name = "CSV municipal para Contabilizei"
        verbose_name_plural = "CSVs municipais para Contabilizei"

    def __str__(self):
        return (
            f"{self.month:%m/%Y} · {self.get_environment_display()} · {self.filename}"
        )
