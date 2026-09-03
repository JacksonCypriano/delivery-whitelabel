import re
from django import forms


class PurchaseForm(forms.Form):
    quote = forms.CharField(widget=forms.HiddenInput)
    name = forms.CharField(label="Nome / razão social", max_length=150)
    document = forms.CharField(label="CPF ou CNPJ do pagador", max_length=20)
    email = forms.EmailField(label="E-mail financeiro")

    def clean_document(self):
        doc = re.sub(r"[.\-/\s]", "", self.cleaned_data["document"]).upper()
        if not (
            re.fullmatch(r"\d{11}", doc) or re.fullmatch(r"[A-Z0-9]{12}\d{2}", doc)
        ):
            raise forms.ValidationError(
                "Informe CPF ou CNPJ completo. A validade será conferida pelo provedor."
            )
        return doc


class ManualCreditForm(forms.Form):
    tenant_id = forms.IntegerField(widget=forms.HiddenInput)
    token = forms.UUIDField(widget=forms.HiddenInput)
    months = forms.IntegerField(label="Meses a acrescentar", min_value=1, max_value=36)
    reason = forms.CharField(
        label="Motivo e referência do recebimento externo ou cortesia",
        max_length=250,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
