from apps.core.admin import TenantModelAdmin, TenantInlineMixin
from django.contrib import admin, messages
from django import forms
from unfold.admin import ModelAdmin
from unfold.admin import StackedInline, TabularInline

from .onboarding import get_store_setup

from .admin_site import super_admin_site, tenant_admin_site
from .models import BrandConfig, Tenant, DeliveryZone, BusinessHour
from .choices import SaleMode
from apps.billing.models import TenantPaymentAccount
from apps.billing.online import request_subaccount
from apps.billing.provider import BillingError
from apps.billing.asaas_fields import (
    COMPANY_TYPE_CHOICES,
    clean_document as clean_asaas_document,
    document_kind,
    normalize_brazilian_phone,
)


class TenantCreateForm(forms.ModelForm):
    # Estes campos permanecem opcionais no formulário-base para preservar
    # criações internas/legadas de Tenant. O Superadmin usa a subclasse
    # TenantSuperAdminCreateForm, onde ambos são obrigatórios.
    merchant_name = forms.CharField(
        label="Nome do responsável",
        required=False,
        max_length=150,
        help_text="Nome da pessoa que receberá o acesso administrativo da loja.",
    )
    merchant_email = forms.EmailField(
        label="E-mail de acesso",
        required=False,
        help_text="Será usado como login e receberá a senha temporária de primeiro acesso.",
    )
    grant_free_month = forms.BooleanField(
        label="Conceder 1 mês de assinatura grátis",
        required=False,
        help_text="Ativa a loja por um mês e registra o crédito como cortesia administrativa.",
    )

    class Meta:
        model = Tenant
        fields = "__all__"

    def clean_merchant_email(self):
        from django.contrib.auth import get_user_model
        from django.db.models import Q

        email = (self.cleaned_data.get("merchant_email") or "").strip().lower()
        if not email:
            return email

        User = get_user_model()
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            raise forms.ValidationError(
                "Já existe uma conta cadastrada com este e-mail. Use outro e-mail ou gerencie a conta existente em Usuários."
            )
        return email

    def clean(self):
        cleaned = super().clean()
        merchant_name = (cleaned.get("merchant_name") or "").strip()
        merchant_email = (cleaned.get("merchant_email") or "").strip()
        if bool(merchant_name) != bool(merchant_email):
            raise forms.ValidationError(
                "Informe o nome do responsável e o e-mail de acesso juntos."
            )
        return cleaned


class TenantSuperAdminCreateForm(TenantCreateForm):
    """Formulário do cadastro combinado Loja + Usuário no Superadmin."""

    merchant_name = forms.CharField(
        label="Nome do responsável",
        required=True,
        max_length=150,
        help_text="Nome da pessoa que receberá o acesso administrativo da loja.",
    )
    merchant_email = forms.EmailField(
        label="E-mail de acesso",
        required=True,
        help_text="Será usado como login e receberá a senha temporária de primeiro acesso.",
    )


class TenantChangeForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = "__all__"


# ── Admin Global (só Tenant) ──────────────────────────────────────────────────
class TenantAdmin(ModelAdmin):
    form = TenantChangeForm
    list_display = ("name", "slug", "whatsapp_number", "merchant_access", "fulfillment_mode", "setup_status", "is_active", "created_at")
    list_filter = ("is_active", "fulfillment_mode")
    search_fields = ("name", "slug", "whatsapp_number")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)

    fieldsets = (
        ("Loja", {"fields": ("name", "slug", "whatsapp_number")}),
        ("Operação", {"fields": ("fulfillment_mode", "is_active")}),
        ("Informações", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    add_fieldsets = (
        (
            "Dados da loja",
            {"fields": ("name", "slug", "whatsapp_number", "grant_free_month")},
        ),
        (
            "Acesso do lojista",
            {
                "fields": ("merchant_name", "merchant_email"),
                "description": (
                    "Ao salvar, o sistema criará o usuário administrador da loja, gerará uma senha temporária "
                    "e enviará por e-mail o login, a senha, o link da loja e o link do painel."
                ),
            },
        ),
        ("Operação", {"fields": ("fulfillment_mode", "is_active")}),
    )

    def get_form(self, request, obj=None, **kwargs):
        kwargs["form"] = TenantSuperAdminCreateForm if obj is None else TenantChangeForm
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        return self.add_fieldsets if obj is None else self.fieldsets

    @admin.display(description="Acesso do lojista")
    def merchant_access(self, obj):
        user = obj.users.filter(is_tenant_admin=True).order_by("pk").first()
        if not user:
            return "Sem usuário"
        if user.must_change_password:
            return f"{user.email or user.username} — primeiro acesso pendente"
        return user.email or user.username

    @staticmethod
    def _split_merchant_name(full_name):
        parts = (full_name or "").strip().split()
        if not parts:
            return "", ""
        return parts[0], " ".join(parts[1:])

    def save_model(self, request, obj, form, change):
        from django.db import transaction
        from apps.accounts.merchant_onboarding import (
            generate_temporary_password,
            schedule_merchant_welcome_email,
        )
        from apps.accounts.models import User
        from apps.billing.models import Subscription
        from apps.billing.services import set_store, audit, extend_locked

        with transaction.atomic():
            # O Superadmin não escolhe o canal de recebimento. Toda loja nova
            # começa no fluxo via WhatsApp; o próprio lojista pode ativar
            # recebimento online depois no painel da loja.
            if not change:
                obj.sale_mode = SaleMode.WHATSAPP

            super().save_model(request, obj, form, change)
            sub=Subscription.objects.select_for_update().get(tenant=obj)
            if not change and form.cleaned_data.get("grant_free_month"):
                extend_locked(
                    sub,
                    1,
                    actor=request.user,
                    reason="Cortesia administrativa: 1 mês grátis no cadastro",
                )
            if 'is_active' in form.changed_data:
                sub.manually_blocked = not obj.is_active
                sub.save(update_fields=['manually_blocked'])
                audit(sub,'Ativação manual da loja', 'Ativar' if obj.is_active else 'Suspender',request.user)
            set_store(sub)

            if not change:
                email = (form.cleaned_data.get("merchant_email") or "").strip().lower()
                merchant_name = (form.cleaned_data.get("merchant_name") or "").strip()

                # No Superadmin estes campos são obrigatórios pelo
                # TenantSuperAdminCreateForm. A condição mantém compatibilidade
                # com criações internas/legadas que usam TenantCreateForm.
                if email and merchant_name:
                    first_name, last_name = self._split_merchant_name(merchant_name)
                    temporary_password = generate_temporary_password()
                    user = User(
                        username=email,
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        tenant=obj,
                        is_active=True,
                        is_staff=True,
                        is_tenant_admin=True,
                        must_change_password=True,
                        welcome_email_sent_at=None,
                    )
                    user.set_password(temporary_password)
                    user.save()
                    schedule_merchant_welcome_email(user.pk, temporary_password)

                    messages.success(
                        request,
                        f"Loja e acesso de {email} criados. O e-mail de boas-vindas será enviado após a gravação.",
                    )

    @admin.display(description="Configuração")
    def setup_status(self, obj):
        setup = get_store_setup(obj)
        return "Pronta" if setup["complete"] else f"Pendente ({setup['completed']}/{setup['total']})"


super_admin_site.register(Tenant, TenantAdmin)


class DeliveryZoneInline(TenantInlineMixin, TabularInline):
    model = DeliveryZone
    extra = 1
    fields = ('city', 'neighborhood', 'fee', 'is_active')


class BusinessHourInline(TenantInlineMixin, TabularInline):
    model = BusinessHour

    fields = (
        "weekday",
        "is_closed",
        "opening_time",
        "closing_time",
    )

    ordering = (
        "weekday",
        "opening_time",
    )

    extra = 1

    can_delete = True


class TenantPaymentAccountForm(forms.ModelForm):
    # Campos declarados explicitamente para a interface seguir a referência do
    # Asaas sem transformar a decisão de ativar em obrigatoriedade permanente
    # quando o recebimento online está desligado.
    document = forms.CharField(
        label="CPF / CNPJ",
        required=False,
        max_length=18,
        help_text="CPF: 000.000.000-00. CNPJ: 00.000.000/0000-00. A pontuação é apenas visual; o sistema envia o documento normalizado ao Asaas.",
    )
    mobile_phone = forms.CharField(
        label="Celular",
        required=False,
        max_length=20,
        help_text="Informe DDD + número. Ex.: (11) 99999-9999. Se o cadastro tiver +55, o sistema remove o código do país antes de enviar ao Asaas.",
    )
    phone = forms.CharField(
        label="Telefone fixo",
        required=False,
        max_length=20,
        help_text="Opcional. Informe DDD + número. Ex.: (11) 3230-0606.",
    )
    company_type = forms.ChoiceField(
        label="Tipo de empresa",
        required=False,
        choices=COMPANY_TYPE_CHOICES,
        help_text="Obrigatório para CNPJ. Escolha a natureza aceita pelo cadastro de subconta do Asaas.",
    )
    income_value = forms.DecimalField(
        label="Faturamento / renda mensal",
        required=False,
        min_value=0.01,
        max_digits=12,
        decimal_places=2,
        localize=True,
        widget=forms.TextInput(),
        help_text="Obrigatório. Informe o faturamento mensal (CNPJ) ou renda mensal (CPF), em reais. Ex.: 25000,00.",
    )

    class Meta:
        model = TenantPaymentAccount
        fields = "__all__"

    def __init__(self, *args, tenant_context=None, **kwargs):
        super().__init__(*args, **kwargs)

        tenant = tenant_context
        if tenant is None and getattr(self.instance, "tenant_id", None):
            tenant = self.instance.tenant

        self.fields["enabled"].label = "Quero receber pagamentos online além do WhatsApp"
        self.fields["enabled"].help_text = ""
        self.fields["enabled"].widget.attrs.update({
            "class": "payment-online-toggle",
            "style": "display:none !important;",
            "data-payment-account-status": (
                self.instance.get_status_display()
                if getattr(self.instance, "pk", None)
                else ""
            ),
            # Estado realmente persistido. O JS usa este valor para que uma
            # tentativa não salva nunca finja estar ativa ao voltar à tela.
            "data-payment-account-saved-enabled": (
                "1" if bool(getattr(self.instance, "enabled", False)) else "0"
            ),
        })
        self.fields["terms_accepted"].label = "Condições aceitas"
        self.fields["terms_accepted"].widget = forms.HiddenInput()

        onboarding_fields = (
            "legal_name", "document", "email", "mobile_phone", "phone", "birth_date",
            "company_type", "income_value", "address", "address_number", "complement",
            "province", "postal_code",
        )
        for name in onboarding_fields:
            current_class = self.fields[name].widget.attrs.get("class", "")
            self.fields[name].widget.attrs["class"] = (
                f"{current_class} payment-onboarding-field".strip()
            )

        self.fields["legal_name"].help_text = (
            "Use o nome completo (CPF) ou a razão social (CNPJ) exatamente como consta no documento."
        )
        self.fields["legal_name"].widget.attrs.update({
            "placeholder": "Nome completo ou razão social",
            "autocomplete": "name",
        })
        self.fields["email"].help_text = (
            "O Asaas utiliza este e-mail na ativação da subconta. Confira antes de salvar."
        )
        self.fields["email"].widget.attrs.update({
            "placeholder": "financeiro@loja.com.br",
            "autocomplete": "email",
        })
        self.fields["document"].widget.attrs.update({
            "placeholder": "000.000.000-00 ou 00.000.000/0000-00",
            "autocomplete": "off",
            "data-payment-document": "1",
        })
        self.fields["mobile_phone"].widget.attrs.update({
            "placeholder": "(11) 99999-9999",
            "inputmode": "tel",
            "autocomplete": "tel",
            "data-payment-phone": "mobile",
        })
        self.fields["phone"].widget.attrs.update({
            "placeholder": "(11) 3230-0606",
            "inputmode": "tel",
            "autocomplete": "tel",
            "data-payment-phone": "landline",
        })

        self.fields["birth_date"].widget = forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "type": "date",
                "class": "payment-onboarding-field payment-field-small",
                "autocomplete": "bday",
            },
        )
        self.fields["birth_date"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
        self.fields["birth_date"].help_text = "Obrigatório somente quando o titular for pessoa física (CPF)."

        self.fields["income_value"].widget.attrs.update({
            "placeholder": "Ex.: 25000,00",
            "inputmode": "decimal",
            "autocomplete": "off",
        })
        self.fields["postal_code"].help_text = (
            "Informe um CEP válido. O Asaas usa o CEP para identificar a cidade e pode recusar um CEP não localizado."
        )
        self.fields["postal_code"].widget.attrs.update({
            "placeholder": "00000-000",
            "inputmode": "numeric",
            "autocomplete": "postal-code",
            "data-payment-cep": "1",
        })
        self.fields["address"].widget.attrs.update({
            "placeholder": "Preenchido automaticamente pelo CEP",
            "autocomplete": "street-address",
        })
        self.fields["address_number"].help_text = "Obrigatório. Informe o número do endereço; quando aplicável, use S/N."
        self.fields["address_number"].widget.attrs.update({
            "placeholder": "Ex.: 544",
            "autocomplete": "address-line2",
        })
        self.fields["complement"].help_text = "Opcional. Ex.: Sala 502, Fundos, Loja 2."
        self.fields["complement"].widget.attrs.update({
            "placeholder": "Complemento (opcional)",
        })
        self.fields["province"].help_text = "Bairro do endereço. Normalmente é preenchido automaticamente pelo CEP."
        self.fields["province"].widget.attrs.update({
            "placeholder": "Preenchido automaticamente pelo CEP",
        })

        if not self.is_bound and tenant is not None:
            self._prefill_from_existing_data(tenant)

    def _set_initial_if_blank(self, field_name, value):
        if value in (None, ""):
            return
        current = getattr(self.instance, field_name, None)
        if current not in (None, ""):
            return
        if self.initial.get(field_name) not in (None, ""):
            return
        self.initial[field_name] = value

    def _prefill_from_existing_data(self, tenant):
        from apps.billing.models import BillingCustomer

        billing_customer = (
            BillingCustomer.objects.filter(tenant=tenant).order_by("-pk").first()
        )
        merchant = tenant.users.filter(is_tenant_admin=True).order_by("pk").first()

        merchant_name = ""
        merchant_email = ""
        if merchant is not None:
            merchant_name = merchant.get_full_name().strip()
            merchant_email = (merchant.email or merchant.username or "").strip()

        self._set_initial_if_blank(
            "legal_name",
            (billing_customer.name if billing_customer else "")
            or merchant_name
            or tenant.name,
        )
        self._set_initial_if_blank(
            "document",
            billing_customer.document if billing_customer else "",
        )
        self._set_initial_if_blank(
            "email",
            (billing_customer.email if billing_customer else "") or merchant_email,
        )
        # O cadastro da loja usa 55 + DDD + telefone. Para o campo Asaas
        # mostramos DDD + número e o backend normaliza novamente no envio.
        try:
            mobile = normalize_brazilian_phone(tenant.whatsapp_number, mobile=True)
        except ValueError:
            mobile = tenant.whatsapp_number
        self._set_initial_if_blank("mobile_phone", mobile)

        self._set_initial_if_blank("postal_code", tenant.pickup_zip_code)
        self._set_initial_if_blank("address", tenant.pickup_address)
        self._set_initial_if_blank("address_number", tenant.pickup_number)
        self._set_initial_if_blank("complement", tenant.pickup_complement)
        self._set_initial_if_blank("province", tenant.pickup_neighborhood)

    class Media:
        css = {"all": ("css/admin/payment-account.css",)}
        js = ("js/admin/payment-account.js",)


    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("enabled"):
            return cleaned

        # Só validamos os dados Asaas quando o lojista está realmente
        # solicitando o recebimento online. Com o switch desligado, os campos
        # ficam preservados sem bloquear outras alterações da loja.
        document = cleaned.get("document", "")
        if document:
            try:
                cleaned["document"] = clean_asaas_document(document)
            except ValueError as exc:
                self.add_error("document", str(exc))

        mobile_phone = cleaned.get("mobile_phone", "")
        if mobile_phone:
            try:
                cleaned["mobile_phone"] = normalize_brazilian_phone(
                    mobile_phone, required=False, mobile=True
                )
            except ValueError as exc:
                self.add_error("mobile_phone", str(exc))

        phone = cleaned.get("phone", "")
        if phone:
            try:
                cleaned["phone"] = normalize_brazilian_phone(
                    phone, required=False, mobile=False
                )
            except ValueError as exc:
                self.add_error("phone", str(exc))

        if not cleaned.get("terms_accepted"):
            self.add_error(
                "terms_accepted",
                "Leia o aviso e confirme a concordância antes de ativar o pagamento online.",
            )

        required_labels = {
            "legal_name": "Informe o nome completo ou a razão social.",
            "document": "Informe um CPF ou CNPJ válido.",
            "email": "Informe o e-mail que será usado na ativação da conta Asaas.",
            "mobile_phone": "Informe o celular com DDD.",
            "income_value": "Informe o faturamento ou a renda mensal.",
            "postal_code": "Informe o CEP.",
            "address": "Informe o logradouro.",
            "address_number": "Informe o número do endereço.",
            "province": "Informe o bairro.",
        }
        for field_name, message in required_labels.items():
            if cleaned.get(field_name) in (None, "") and field_name not in self.errors:
                self.add_error(field_name, message)

        kind = document_kind(cleaned.get("document"))
        if kind == "CPF" and not cleaned.get("birth_date"):
            self.add_error("birth_date", "A data de nascimento é obrigatória para cadastro com CPF.")
        elif kind == "CNPJ" and not cleaned.get("company_type"):
            self.add_error("company_type", "Selecione o tipo da empresa para cadastro com CNPJ.")

        return cleaned


class TenantPaymentAccountInline(TenantInlineMixin, StackedInline):
    model = TenantPaymentAccount
    form = TenantPaymentAccountForm
    extra = 1
    max_num = 1
    can_delete = False
    classes = ("payment-account-inline",)
    readonly_fields = ("status", "provider_account_id", "activation_url", "last_error")

    fieldsets = (
        (
            "Recebimento online",
            {
                # O status não é exibido como uma linha separada. Ele é enviado
                # ao controle compacto por data-attribute e aparece apenas como
                # badge ao lado do switch.
                "fields": ("terms_accepted", "enabled"),
                "classes": ("payment-online-control-section",),
            },
        ),
        (
            "Dados do responsável / empresa",
            {
                "fields": (
                    "legal_name",
                    "document",
                    "email",
                    "mobile_phone",
                    "phone",
                    "birth_date",
                    "company_type",
                    "income_value",
                ),
                "classes": ("payment-online-details-section",),
            },
        ),
        (
            "Endereço",
            {
                "fields": (
                    "postal_code",
                    "address",
                    "address_number",
                    "complement",
                    "province",
                ),
                "classes": ("payment-online-details-section",),
                "description": (
                    "Informe primeiro o CEP. O sistema preencherá automaticamente "
                    "logradouro, bairro e complemento quando disponíveis; informe o número "
                    "e ajuste o complemento se necessário."
                ),
            },
        ),
        (
            "Integração Asaas",
            {
                "fields": ("provider_account_id", "activation_url", "last_error"),
                "classes": ("payment-online-details-section", "collapse"),
            },
        ),
    )

    def get_formset(self, request, obj=None, **kwargs):
        formset_class = super().get_formset(request, obj, **kwargs)
        tenant = obj or getattr(request, "tenant", None)

        # Passa o tenant ao ModelForm inclusive no primeiro cadastro, quando a
        # instância TenantPaymentAccount ainda não possui tenant_id durante o
        # __init__ do formulário.
        class TenantContextFormSet(formset_class):
            def get_form_kwargs(self, index):
                form_kwargs = super().get_form_kwargs(index)
                form_kwargs["tenant_context"] = tenant
                return form_kwargs

        return TenantContextFormSet

    def get_extra(self, request, obj=None, **kwargs):
        if obj is not None and TenantPaymentAccount.objects.filter(tenant=obj).exists():
            return 0
        return 1

# ── Admin do Lojista: Configurações da Loja (Tenant) ─────────────────────────
class StoreSettingsAdmin(ModelAdmin):
    """
    Permite ao lojista editar as informações da própria loja.
    """

    list_display = (
        "name",
        "whatsapp_number",
        "is_active",
    )

    readonly_fields = (
        "slug",
        "is_active",
        "created_at",
    )

    fieldsets = (
        (
            "Informações da loja",
            {
                "fields": (
                    "name",
                    "slug",
                    "whatsapp_number",
                    "fulfillment_mode",
                ),
            },
        ),
        (
            "Endereço para retirada",
            {
                "fields": (
                    "pickup_address",
                    "pickup_number",
                    "pickup_complement",
                    "pickup_neighborhood",
                    "pickup_city",
                    "pickup_zip_code",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_active",
                    "created_at",
                ),
                "description": "A ativação da loja é controlada pelo gestor do VemDeDelivery. Para aparecer no marketplace, conclua o checklist do painel e publique o perfil da loja.",
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        from django.db import transaction
        from apps.billing.models import Subscription
        from apps.billing.services import set_store
        with transaction.atomic():
            sub=Subscription.objects.select_for_update().get(tenant=obj)
            obj.is_active = Tenant.objects.get(pk=obj.pk).is_active
            super().save_model(request,obj,form,change)
            set_store(sub)

    def get_inlines(self, request, obj=None):
        inlines = [BusinessHourInline, TenantPaymentAccountInline]

        if obj is None or obj.accepts_delivery:
            inlines.append(DeliveryZoneInline)

        return inlines

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is TenantPaymentAccount:
            account = TenantPaymentAccount.objects.filter(tenant=request.tenant).first()
            if account and account.enabled and not account.provider_account_id:
                try:
                    request_subaccount(account)
                except BillingError as exc:
                    messages.error(request, str(exc))

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        tenant = getattr(request, "tenant", None)

        if not tenant:
            return qs.none()

        return qs.filter(pk=tenant.pk)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return True

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


tenant_admin_site.register(Tenant, StoreSettingsAdmin)


# ── Admin do Lojista (BrandConfig) ───────────────────────────────────────────
class TenantBrandConfigAdmin(ModelAdmin):
    list_display = (
        "tenant",
        "primary_color",
        "secondary_color",
        "background_color",
        "dark_mode_enabled",
    )

    readonly_fields = ("tenant",)

    fieldsets = (
        (
            "Identidade visual",
            {
                "fields": (
                    "primary_color",
                    "secondary_color",
                    "accent_color",
                    "background_color",
                    "card_background_color",
                    "text_color",
                    "muted_text_color",
                    "border_color",
                    "button_text_color",
                    "success_color",
                    "warning_color",
                    "danger_color",
                )
            },
        ),
        (
            "Tipografia",
            {
                "fields": (
                    "font_family",
                    "base_font_size",
                )
            },
        ),
        (
            "Cartões e botões",
            {
                "fields": (
                    "border_radius",
                    "button_radius",
                    "card_shadow",
                    "hover_effect",
                )
            },
        ),
        (
            "Layout da loja",
            {
                "fields": (
                    "header_style",
                    "show_search_bar",
                    "show_category_icons",
                    "show_product_description",
                    "show_product_image",
                    "compact_product_cards",
                )
            },
        ),
        (
            "Modo escuro",
            {
                "fields": (
                    "dark_mode_enabled",
                    "dark_mode_primary",
                    "dark_mode_background",
                    "dark_mode_card_background",
                    "dark_mode_text",
                    "dark_mode_muted_text",
                    "dark_mode_border_color",
                )
            },
        ),
        (
            "Imagens da marca",
            {
                "fields": (
                    "logo",
                    "favicon",
                    "banner",
                )
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        tenant = getattr(request, "tenant", None)

        if not tenant:
            return qs.none()

        return qs.filter(tenant=tenant)

    def save_model(self, request, obj, form, change):
        if not obj.tenant_id:
            obj.tenant = getattr(request, "tenant", None)

        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        return True

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        tenant = getattr(request, "tenant", None)

        if not tenant:
            return False

        return not BrandConfig.objects.filter(tenant=tenant).exists()

    def has_delete_permission(self, request, obj=None):
        return True


tenant_admin_site.register(BrandConfig, TenantBrandConfigAdmin)

@admin.register(DeliveryZone, site=tenant_admin_site)
class DeliveryZoneAdmin(TenantModelAdmin):
    list_display = ("city", "neighborhood", "fee", "is_active")
    list_editable = ("is_active",)
    list_filter = ("city", "is_active")
    search_fields = ("city", "neighborhood")

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        tenant = getattr(request, "tenant", None)

        if not tenant or not tenant.accepts_delivery:
            return qs.none()

        return qs.filter(tenant=tenant)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.tenant = request.tenant

        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        tenant = getattr(request, "tenant", None)
        return bool(tenant and tenant.accepts_delivery)


    def has_view_permission(self, request, obj=None):
        tenant = getattr(request, "tenant", None)
        return bool(tenant and tenant.accepts_delivery)


    def has_add_permission(self, request):
        tenant = getattr(request, "tenant", None)
        return bool(tenant and tenant.accepts_delivery)


    def has_change_permission(self, request, obj=None):
        tenant = getattr(request, "tenant", None)
        return bool(tenant and tenant.accepts_delivery)


    def has_delete_permission(self, request, obj=None):
        tenant = getattr(request, "tenant", None)
        return bool(tenant and tenant.accepts_delivery)


@admin.register(BusinessHour, site=tenant_admin_site)
class BusinessHourAdmin(ModelAdmin):
    list_display = (
        "tenant",
        "weekday",
        "is_closed",
        "opening_time",
        "closing_time",
    )

    list_filter = (
        "tenant",
        "weekday",
        "is_closed",
    )

    ordering = (
        "tenant",
        "weekday",
    )

    readonly_fields = (
        "tenant",
        "weekday",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        tenant = getattr(request, "tenant", None)

        if not tenant:
            return qs.none()

        return qs.filter(tenant=tenant)

    def has_module_permission(self, request):
        return True

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
