import uuid
from .fiscal_models import FiscalSettings, TaxRate, FiscalInvoice, FiscalCustomerRule, MunicipalExport
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


ENVIRONMENTS = [
    ("sandbox", "Ambiente de testes"),
    ("production", "Produção"),
]


class BillingSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    grace_days = models.PositiveSmallIntegerField(
        "Dias de tolerância", default=3, validators=[MaxValueValidator(90)]
    )
    pix_enabled = models.BooleanField("Pix habilitado", default=True)
    boleto_enabled = models.BooleanField("Boleto habilitado", default=False)
    card_enabled = models.BooleanField("Crédito à vista habilitado", default=False)
    fixed_pix_fee = models.DecimalField(
        "Taxa Pix/boleto para cálculo (R$)",
        max_digits=7,
        decimal_places=2,
        default=Decimal("1.99"),
        validators=[MinValueValidator(0)],
    )
    card_percent = models.DecimalField(
        "Taxa crédito (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.99"),
        validators=[MinValueValidator(0), MaxValueValidator(50)],
    )
    card_fixed_fee = models.DecimalField(
        "Taxa fixa crédito (R$)",
        max_digits=7,
        decimal_places=2,
        default=Decimal("0.49"),
        validators=[MinValueValidator(0)],
    )

    class Meta:
        verbose_name = "Configuração de cobrança"
        verbose_name_plural = "Configuração de cobrança"

    def __str__(self):
        return "Formas de pagamento e tolerância"

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]


class Plan(models.Model):
    name = models.CharField("Plano", max_length=80)
    months = models.PositiveSmallIntegerField(
        "Meses", unique=True, validators=[MinValueValidator(1), MaxValueValidator(36)]
    )
    monthly_price = models.DecimalField(
        "Valor mensal de referência",
        max_digits=9,
        decimal_places=2,
        default=199,
        validators=[MinValueValidator(Decimal("1"))],
    )
    discount = models.DecimalField(
        "Desconto (%)",
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(90)],
    )
    active = models.BooleanField("Disponível para compra", default=True)

    class Meta:
        ordering = ["months"]
        verbose_name = "Plano"
        verbose_name_plural = "Planos"

    @property
    def price(self):
        return (self.monthly_price * self.months * (1 - self.discount / 100)).quantize(
            Decimal(".01")
        )

    def __str__(self):
        return self.name


class AdditionalService(models.Model):
    """Serviço avulso contratado por uma loja, sem alterar a assinatura."""
    code = models.SlugField("Código", unique=True)
    name = models.CharField("Serviço", max_length=120)
    description = models.CharField("Descrição", max_length=300, blank=True)
    price = models.DecimalField("Valor", max_digits=9, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    active = models.BooleanField("Disponível para contratação", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Serviço adicional"
        verbose_name_plural = "Serviços adicionais"

    def __str__(self):
        return self.name


class Subscription(models.Model):
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="subscription",
        verbose_name="Loja",
    )
    managed = models.BooleanField(
        "Controlar vencimento desta loja",
        default=False,
        help_text="Lojas existentes ficam sem cobrança automática até você definir o vencimento e habilitar este controle.",
    )
    valid_until = models.DateField(
        "Vencimento",
        null=True,
        blank=True,
        help_text="Primeiro dia do novo período. A tolerância conta a partir desta data.",
    )
    anchor_day = models.PositiveSmallIntegerField("Dia-base do vencimento", default=1, editable=False)
    grace_days = models.PositiveSmallIntegerField(
        "Tolerância específica (dias)",
        null=True,
        blank=True,
        validators=[MaxValueValidator(90)],
        help_text="Vazio: usar configuração geral.",
    )
    manually_blocked = models.BooleanField(
        "Suspensão administrativa",
        default=False,
        help_text="Pagamento não remove esta suspensão.",
    )
    billing_suspended = models.BooleanField(
        "Suspensa por assinatura", default=False, editable=False
    )
    payment_review = models.BooleanField(
        "Bloqueio por estorno/contestação",
        default=False,
        help_text="Revise os pagamentos antes de desmarcar.",
    )
    created_at = models.DateTimeField("Criada em", auto_now_add=True)

    class Meta:
        verbose_name = "Assinatura da loja"
        verbose_name_plural = "Assinaturas das lojas"

    def __str__(self):
        return str(self.tenant)

    @property
    def days_remaining(self):
        return (
            (self.valid_until - timezone.localdate()).days if self.valid_until else None
        )

    @property
    def situation(self):
        if self.manually_blocked:
            return "Suspensão administrativa"
        if self.payment_review:
            return "Pagamento em revisão"
        if not self.managed:
            return "Isenta / controle não iniciado"
        if self.billing_suspended:
            return "Suspensa por vencimento"
        if self.valid_until is None:
            return "Aguardando primeiro pagamento"
        if self.days_remaining <= 0:
            return "Vencida / tolerância"
        if self.days_remaining <= 7:
            return "Próxima do vencimento"
        return "Em dia"


class BillingCustomer(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, verbose_name="Loja")
    environment = models.CharField("Ambiente", max_length=12, choices=ENVIRONMENTS)
    provider_id = models.CharField("ID no Asaas", max_length=80, blank=True)
    name = models.CharField("Nome / razão social", max_length=150)
    document = models.CharField("CPF / CNPJ", max_length=14)
    email = models.EmailField("E-mail")
    attempted = models.BooleanField("Cadastro já solicitado ao Asaas", default=False)

    class Meta:
        verbose_name = "Pagador no Asaas"
        verbose_name_plural = "Pagadores no Asaas"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "environment"], name="billing_customer_tenant_env"
            )
        ]


class Invoice(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "Preparando"
        UNCERTAIN = "UNCERTAIN", "Aguardando conciliação"
        PENDING = "PENDING", "Aguardando pagamento"
        OVERDUE = "OVERDUE", "Cobrança vencida"
        PAID = "PAID", "Pagamento confirmado"
        CANCELLED = "CANCELLED", "Cancelada"
        REVIEW = "REVIEW", "Estorno / contestação"
        ERROR = "ERROR", "Falha de emissão"

    METHODS = [("PIX", "Pix"), ("BOLETO", "Boleto"), ("CREDIT_CARD", "Crédito à vista")]
    id = models.UUIDField("ID", primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.PROTECT, verbose_name="Loja"
    )
    additional_service = models.ForeignKey(AdditionalService, null=True, blank=True, on_delete=models.PROTECT, verbose_name="Serviço adicional")
    plan_name = models.CharField("Plano comprado", max_length=80)
    months = models.PositiveSmallIntegerField("Meses comprados", default=0)
    amount = models.DecimalField("Valor cobrado", max_digits=12, decimal_places=2)
    method = models.CharField("Forma de pagamento", max_length=12, choices=METHODS)
    environment = models.CharField("Ambiente", max_length=12, choices=ENVIRONMENTS)
    provider_id = models.CharField(
        "ID Asaas", max_length=80, unique=True, null=True, blank=True
    )
    customer_id_external = models.CharField("ID do pagador no Asaas", max_length=80, blank=True)
    checkout_url = models.URLField("Link de pagamento", max_length=600, blank=True)
    status = models.CharField(
        "Situação", max_length=12, choices=Status.choices, default=Status.NEW
    )
    created_at = models.DateTimeField("Criada em", auto_now_add=True)
    paid_at = models.DateTimeField("Confirmada em", null=True, blank=True)
    due_date = models.DateField("Vencimento da cobrança")
    last_checked_at = models.DateTimeField("Última consulta ao Asaas", null=True, blank=True)
    issuance_attempted = models.BooleanField("Emissão já solicitada ao Asaas", default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Cobrança"
        verbose_name_plural = "Cobranças"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="billing_invoice_positive"
            )
        ]

    def __str__(self):
        return f"{self.tenant} · {self.plan_name} · {self.get_status_display()}"

    @property
    def reference(self):
        """Stable external reference used to reconcile this invoice in Asaas."""
        return f"vdd-billing:{self.environment}:{self.pk}"


class TenantPaymentAccount(models.Model):
    """Asaas subconta that receives a tenant's online orders.

    The API key is encrypted at rest and is never exposed to tenant users.
    This account is intentionally separate from the platform billing customer
    used for subscription invoices.
    """
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Solicitação registrada"
        PENDING = "PENDING", "Aguardando ativação no Asaas"
        APPROVED = "APPROVED", "Aprovada"
        REJECTED = "REJECTED", "Revisar cadastro"
        ERROR = "ERROR", "Falha de configuração"

    tenant = models.OneToOneField(
        "tenants.Tenant", on_delete=models.PROTECT, related_name="payment_account", verbose_name="Loja"
    )
    enabled = models.BooleanField("Pagamento online solicitado", default=False)
    terms_accepted = models.BooleanField("Concordou com taxas e condições", default=False)
    terms_accepted_at = models.DateTimeField("Concordância registrada em", null=True, blank=True)
    status = models.CharField("Situação", max_length=20, choices=Status.choices, default=Status.REQUESTED)
    legal_name = models.CharField("Nome / razão social", max_length=150, blank=True)
    document = models.CharField("CPF / CNPJ", max_length=14, blank=True)
    email = models.EmailField("E-mail de ativação", blank=True)
    mobile_phone = models.CharField("Celular", max_length=20, blank=True)
    phone = models.CharField("Telefone fixo", max_length=20, blank=True)
    birth_date = models.DateField("Data de nascimento (CPF)", null=True, blank=True)
    company_type = models.CharField("Tipo de empresa", max_length=20, blank=True)
    income_value = models.DecimalField("Faturamento / renda mensal", max_digits=12, decimal_places=2, null=True, blank=True)
    address = models.CharField("Logradouro", max_length=255, blank=True)
    address_number = models.CharField("Número", max_length=20, blank=True)
    complement = models.CharField("Complemento", max_length=100, blank=True)
    province = models.CharField("Bairro", max_length=100, blank=True)
    postal_code = models.CharField("CEP", max_length=9, blank=True)
    provider_account_id = models.CharField("ID da subconta Asaas", max_length=80, blank=True)
    wallet_id = models.CharField("Wallet ID Asaas", max_length=80, blank=True)
    encrypted_api_key = models.TextField("Chave Asaas criptografada", blank=True, editable=False)
    activation_url = models.URLField("Link de ativação", max_length=600, blank=True)
    last_error = models.CharField("Último erro", max_length=500, blank=True)
    requested_at = models.DateTimeField("Solicitada em", null=True, blank=True)
    approved_at = models.DateTimeField("Aprovada em", null=True, blank=True)
    created_at = models.DateTimeField("Criada em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizada em", auto_now=True)

    class Meta:
        verbose_name = "Conta de pagamentos online"
        verbose_name_plural = "Contas de pagamentos online"

    def __str__(self):
        return f"{self.tenant} · {self.get_status_display()}"

    @property
    def is_ready(self):
        return self.enabled and self.status == self.Status.APPROVED and bool(self.provider_account_id and self.encrypted_api_key)

    def set_api_key(self, value):
        from .secrets import encrypt_secret
        self.encrypted_api_key = encrypt_secret(value)

    def save(self, *args, **kwargs):
        if self.terms_accepted and self.terms_accepted_at is None:
            self.terms_accepted_at = timezone.now()
        if not self.terms_accepted:
            self.enabled = False

        super().save(*args, **kwargs)

        # sale_mode é um estado interno derivado da decisão do lojista.
        # A loja sempre continua aceitando o fluxo via WhatsApp; quando a
        # subconta é habilitada, também liberamos o pagamento online.
        from apps.tenants.choices import SaleMode
        from apps.tenants.models import Tenant

        desired_sale_mode = (
            SaleMode.ONLINE if self.is_ready else SaleMode.WHATSAPP
        )
        Tenant.objects.filter(pk=self.tenant_id).exclude(
            sale_mode=desired_sale_mode
        ).update(sale_mode=desired_sale_mode)

    def get_api_key(self):
        from .secrets import decrypt_secret
        return decrypt_secret(self.encrypted_api_key)


class OrderPayment(models.Model):
    """Hosted Asaas Checkout created in the store subaccount."""
    class Status(models.TextChoices):
        PENDING = "PENDING", "Aguardando pagamento"
        PAID = "PAID", "Pagamento confirmado"
        CANCELED = "CANCELED", "Cancelado"
        EXPIRED = "EXPIRED", "Expirado"
        ERROR = "ERROR", "Falha no pagamento"

    order = models.OneToOneField("orders.Order", on_delete=models.PROTECT, related_name="online_payment", verbose_name="Pedido")
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, verbose_name="Loja")
    provider_account_id = models.CharField("Subconta Asaas", max_length=80)
    checkout_id = models.CharField("Checkout Asaas", max_length=100, unique=True, blank=True)
    checkout_url = models.URLField("Link de pagamento", max_length=600, blank=True)
    external_reference = models.CharField("Referência externa", max_length=120, unique=True)
    confirmation_code = models.CharField("Código de confirmação", max_length=24, unique=True)
    method = models.CharField("Forma de pagamento", max_length=20)
    amount = models.DecimalField("Valor", max_digits=10, decimal_places=2)
    status = models.CharField("Situação", max_length=12, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField("Confirmado em", null=True, blank=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Pagamento de pedido"
        verbose_name_plural = "Pagamentos de pedidos"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Pedido #{self.order_id} · {self.get_status_display()}"

    @property
    def reference(self):
        return self.external_reference


class Credit(models.Model):
    invoice = models.OneToOneField(
        Invoice, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Cobrança"
    )
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.PROTECT, verbose_name="Loja"
    )
    months = models.PositiveSmallIntegerField(
        "Meses", validators=[MinValueValidator(1), MaxValueValidator(36)]
    )
    previous_until = models.DateField("Vencimento anterior", null=True, blank=True)
    valid_until = models.DateField("Novo vencimento")
    reason = models.CharField("Motivo / comprovante", max_length=250)
    manual_token = models.UUIDField("Identificador do registro manual", unique=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Registrado por"
    )
    created_at = models.DateTimeField("Registrado em", auto_now_add=True)

    class Meta:
        verbose_name = "Crédito de assinatura"
        verbose_name_plural = "Créditos de assinatura"
        ordering = ["-created_at"]


class BillingEvent(models.Model):
    event_id = models.CharField("ID da notificação", max_length=160, unique=True)
    payment_id = models.CharField("ID da cobrança no Asaas", max_length=80)
    kind = models.CharField("Evento do Asaas (código técnico)", max_length=80)
    environment = models.CharField("Ambiente", max_length=12, choices=ENVIRONMENTS)
    processed_at = models.DateTimeField("Processada em", null=True, blank=True)
    attempts = models.PositiveIntegerField("Tentativas", default=0)
    created_at = models.DateTimeField("Recebida em", auto_now_add=True)

    class Meta:
        verbose_name = "Notificação de pagamento"
        verbose_name_plural = "Notificações de pagamento"


class BillingAudit(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.PROTECT, verbose_name="Loja"
    )
    action = models.CharField("Ação", max_length=80)
    detail = models.CharField("Detalhes", max_length=500)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Usuário responsável"
    )
    created_at = models.DateTimeField("Data", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Evento da assinatura"
        verbose_name_plural = "Auditoria de assinaturas"
