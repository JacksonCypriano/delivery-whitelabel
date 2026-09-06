import re

from django import forms
from django.core.validators import MaxLengthValidator
from unfold.widgets import UnfoldBooleanSwitchWidget

from .models import BrandConfig, BusinessHour, DeliveryZone
from .utils import validate_whatsapp_number


BRAZIL_UF_CHOICES = [
    ("", "Selecione a UF"),
    ("AC", "AC - Acre"),
    ("AL", "AL - Alagoas"),
    ("AP", "AP - Amapá"),
    ("AM", "AM - Amazonas"),
    ("BA", "BA - Bahia"),
    ("CE", "CE - Ceará"),
    ("DF", "DF - Distrito Federal"),
    ("ES", "ES - Espírito Santo"),
    ("GO", "GO - Goiás"),
    ("MA", "MA - Maranhão"),
    ("MT", "MT - Mato Grosso"),
    ("MS", "MS - Mato Grosso do Sul"),
    ("MG", "MG - Minas Gerais"),
    ("PA", "PA - Pará"),
    ("PB", "PB - Paraíba"),
    ("PR", "PR - Paraná"),
    ("PE", "PE - Pernambuco"),
    ("PI", "PI - Piauí"),
    ("RJ", "RJ - Rio de Janeiro"),
    ("RN", "RN - Rio Grande do Norte"),
    ("RS", "RS - Rio Grande do Sul"),
    ("RO", "RO - Rondônia"),
    ("RR", "RR - Roraima"),
    ("SC", "SC - Santa Catarina"),
    ("SP", "SP - São Paulo"),
    ("SE", "SE - Sergipe"),
    ("TO", "TO - Tocantins"),
]


class TenantAdminUXMixin:
    """Aplica máscaras/ajudas visuais aos formulários de loja."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "name" in self.fields:
            self.fields["name"].widget.attrs.setdefault("placeholder", "Ex.: Pizzaria do Centro")

        if "slug" in self.fields:
            self.fields["slug"].help_text = (
                "Identificador usado no endereço da loja. Use letras minúsculas, números e hífen. "
                "Ex.: pizzaria-do-centro."
            )
            self.fields["slug"].widget.attrs.update({
                "placeholder": "pizzaria-do-centro",
                "autocomplete": "off",
            })

        if "whatsapp_number" in self.fields:
            # O model guarda apenas 55 + DDD + número (até 13 dígitos), mas o
            # formulário permite a máscara visual e normaliza antes do model.clean().
            whatsapp_field = self.fields["whatsapp_number"]
            whatsapp_field.max_length = 20
            whatsapp_field.validators = [
                validator
                for validator in whatsapp_field.validators
                if not isinstance(validator, MaxLengthValidator)
            ]
            whatsapp_field.validators.append(MaxLengthValidator(20))
            self.fields["whatsapp_number"].help_text = (
                "Informe um celular brasileiro com DDD. Ex.: +55 (11) 99999-9999. "
                "O sistema salva automaticamente no padrão 5511999999999."
            )
            self.fields["whatsapp_number"].widget.attrs.update({
                "placeholder": "+55 (11) 99999-9999",
                "inputmode": "tel",
                "autocomplete": "tel",
                "data-store-whatsapp": "1",
                "maxlength": "20",
            })

        if "fulfillment_mode" in self.fields:
            self.fields["fulfillment_mode"].help_text = (
                "Escolha como o cliente poderá receber o pedido: entrega e retirada, somente retirada ou somente entrega."
            )

        if "pickup_zip_code" in self.fields:
            self.fields["pickup_zip_code"].help_text = (
                "Digite primeiro o CEP. Consultaremos o ViaCEP e preencheremos logradouro, bairro e cidade. "
                "Depois informe apenas o número e, se houver, o complemento."
            )
            self.fields["pickup_zip_code"].widget.attrs.update({
                "placeholder": "00000-000",
                "inputmode": "numeric",
                "autocomplete": "postal-code",
                "data-store-cep": "1",
            })

        if "pickup_address" in self.fields:
            self.fields["pickup_address"].help_text = "Preenchido automaticamente pelo CEP quando disponível. Você pode corrigir se necessário."
            self.fields["pickup_address"].widget.attrs.update({
                "placeholder": "Preenchido automaticamente pelo CEP",
                "autocomplete": "address-line1",
            })

        if "pickup_number" in self.fields:
            self.fields["pickup_number"].help_text = "Informe o número do estabelecimento. Use S/N quando não houver número."
            self.fields["pickup_number"].widget.attrs.update({
                "placeholder": "Ex.: 120 ou S/N",
                "autocomplete": "address-line2",
            })

        if "pickup_complement" in self.fields:
            self.fields["pickup_complement"].help_text = "Opcional. Ex.: Loja 2, Sala 5, Fundos."
            self.fields["pickup_complement"].widget.attrs.update({
                "placeholder": "Ex.: Loja 2 (opcional)",
            })

        if "pickup_neighborhood" in self.fields:
            self.fields["pickup_neighborhood"].help_text = "Preenchido automaticamente pelo CEP quando disponível."
            self.fields["pickup_neighborhood"].widget.attrs.update({
                "placeholder": "Preenchido automaticamente pelo CEP",
                "autocomplete": "address-level3",
            })

        if "pickup_city" in self.fields:
            self.fields["pickup_city"].help_text = "Preenchida automaticamente pelo CEP."
            self.fields["pickup_city"].widget.attrs.update({
                "placeholder": "Preenchida automaticamente pelo CEP",
                "autocomplete": "address-level2",
            })

        if "merchant_name" in self.fields:
            self.fields["merchant_name"].widget.attrs.setdefault("placeholder", "Ex.: João da Silva")

        if "merchant_email" in self.fields:
            self.fields["merchant_email"].widget.attrs.update({
                "placeholder": "Ex.: joao@minhaloja.com.br",
                "autocomplete": "email",
            })

    def clean_whatsapp_number(self):
        value = self.cleaned_data.get("whatsapp_number", "")
        clean = re.sub(r"\D", "", value or "")
        validate_whatsapp_number(clean)
        return clean

    class Media:
        js = ("js/admin/store-settings.js",)


class FriendlyTimeField(forms.TimeField):
    """Aceita horas curtas como 07, 730 e 0730 antes do parser do Django."""

    @staticmethod
    def _normalize_raw_time(value):
        if not isinstance(value, str):
            return value

        raw = value.strip()
        if not raw:
            return raw

        # Se já veio no formato HH:MM, deixa o TimeField validar normalmente.
        if ":" in raw:
            return raw

        digits = re.sub(r"\D", "", raw)
        if not digits or len(digits) > 4:
            return raw

        if len(digits) <= 2:
            hour = int(digits)
            minute = 0
        elif len(digits) == 3:
            hour = int(digits[0])
            minute = int(digits[1:])
        else:
            hour = int(digits[:2])
            minute = int(digits[2:])

        if hour > 23 or minute > 59:
            return raw

        return f"{hour:02d}:{minute:02d}"

    def to_python(self, value):
        return super().to_python(self._normalize_raw_time(value))


class BusinessHourAdminForm(forms.ModelForm):
    """Exibe a regra positiva 'Aberta' sem alterar o campo interno is_closed."""

    is_open = forms.BooleanField(
        label="Loja aberta neste horário",
        required=False,
        widget=UnfoldBooleanSwitchWidget(attrs={"data-business-open": "1"}),
        help_text=(
            "Marque para abrir a loja neste intervalo. Para dois períodos no mesmo dia, "
            "adicione outro horário com o mesmo dia da semana."
        ),
    )
    opening_time = FriendlyTimeField(
        label="Abertura",
        required=False,
        input_formats=["%H:%M", "%H%M", "%H"],
        widget=forms.TextInput(
            attrs={
                "placeholder": "07:00",
                "inputmode": "numeric",
                "maxlength": "5",
                "autocomplete": "off",
                "data-business-time": "1",
            }
        ),
        help_text="Ex.: 07:00. Você também pode digitar apenas 07; o sistema interpreta como 07:00.",
    )
    closing_time = FriendlyTimeField(
        label="Fechamento",
        required=False,
        input_formats=["%H:%M", "%H%M", "%H"],
        widget=forms.TextInput(
            attrs={
                "placeholder": "18:00",
                "inputmode": "numeric",
                "maxlength": "5",
                "autocomplete": "off",
                "data-business-time": "1",
            }
        ),
        help_text=(
            "Ex.: 18:00. Horários após a meia-noite também são aceitos, por exemplo 18:00 até 01:00."
        ),
    )

    class Meta:
        model = BusinessHour
        fields = ("weekday", "opening_time", "closing_time")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["weekday"].help_text = (
            "Escolha o dia. É permitido cadastrar mais de um intervalo no mesmo dia."
        )
        if self.instance and self.instance.pk:
            self.fields["is_open"].initial = not self.instance.is_closed
        else:
            self.fields["is_open"].initial = False

    def clean(self):
        cleaned = super().clean()
        is_open = bool(cleaned.get("is_open"))

        # O ModelForm não expõe is_closed, mas o model.clean() depende dele.
        self.instance.is_closed = not is_open

        if not is_open:
            cleaned["opening_time"] = None
            cleaned["closing_time"] = None
            self.instance.opening_time = None
            self.instance.closing_time = None
            return cleaned

        opening = cleaned.get("opening_time")
        closing = cleaned.get("closing_time")

        if not opening:
            self.add_error("opening_time", "Informe o horário de abertura. Ex.: 07:00.")
        if not closing:
            self.add_error("closing_time", "Informe o horário de fechamento. Ex.: 18:00.")
        if opening and closing and opening == closing:
            self.add_error("closing_time", "O fechamento deve ser diferente da abertura.")

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.is_closed = not bool(self.cleaned_data.get("is_open"))
        if instance.is_closed:
            instance.opening_time = None
            instance.closing_time = None
        if commit:
            instance.save()
        return instance

    class Media:
        js = ("js/admin/store-settings.js",)


class DeliveryZoneAdminForm(forms.ModelForm):
    fee = forms.DecimalField(
        label="Taxa de entrega (R$)",
        max_digits=8,
        decimal_places=2,
        localize=True,
        min_value=0,
        widget=forms.TextInput(attrs={"placeholder": "Ex.: 7,50", "inputmode": "decimal"}),
        help_text="Informe o valor cobrado para esta região. Use 0,00 para entrega grátis.",
    )

    class Meta:
        model = DeliveryZone
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "city" in self.fields:
            self.fields["city"].widget.attrs.setdefault("placeholder", "Ex.: Itapevi")
        if "neighborhood" in self.fields:
            self.fields["neighborhood"].widget.attrs.setdefault("placeholder", "Ex.: Centro")
        if "is_active" in self.fields:
            self.fields["is_active"].label = "Ativa para entrega"
            self.fields["is_active"].help_text = "Desmarque para manter a região cadastrada sem aceitar entregas nela."


class BrandConfigAdminForm(forms.ModelForm):
    class Meta:
        model = BrandConfig
        fields = "__all__"

    COLOR_FIELDS = (
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
        "dark_mode_primary",
        "dark_mode_background",
        "dark_mode_card_background",
        "dark_mode_text",
        "dark_mode_muted_text",
        "dark_mode_border_color",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.COLOR_FIELDS:
            field = self.fields.get(field_name)
            if field is None:
                continue
            if hasattr(field.widget, "input_type"):
                field.widget.input_type = "color"
            field.widget.attrs["data-color-picker"] = "1"
            if not field.help_text:
                field.help_text = "Clique no seletor para escolher a cor."

        for field_name, example in (
            ("base_font_size", "Ex.: 16"),
            ("border_radius", "Ex.: 18"),
            ("button_radius", "Ex.: 12"),
        ):
            field = self.fields.get(field_name)
            if field:
                field.widget.attrs.update({"inputmode": "numeric", "placeholder": example})
