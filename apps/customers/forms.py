from django import forms

from .models import CustomerAddress


class CustomerAddressForm(forms.ModelForm):
    class Meta:
        model = CustomerAddress

        fields = (
            "label",
            "zip_code",
            "street",
            "number",
            "complement",
            "neighborhood",
            "city",
            "state",
            "reference",
            "is_default",
        )

        labels = {
            "label": "Identificação",
            "zip_code": "CEP",
            "street": "Rua / Avenida",
            "number": "Número",
            "complement": "Complemento",
            "neighborhood": "Bairro",
            "city": "Cidade",
            "state": "Estado",
            "reference": "Ponto de referência",
            "is_default": "Definir como endereço principal",
        }

        widgets = {
            "label": forms.TextInput(
                attrs={
                    "placeholder": "Ex.: Casa, Trabalho, Apartamento",
                }
            ),
            "zip_code": forms.TextInput(
                attrs={
                    "placeholder": "00000-000",
                    "inputmode": "numeric",
                }
            ),
            "street": forms.TextInput(
                attrs={
                    "placeholder": "Rua / Avenida",
                }
            ),
            "number": forms.TextInput(
                attrs={
                    "placeholder": "Número",
                }
            ),
            "complement": forms.TextInput(
                attrs={
                    "placeholder": "Apartamento, bloco, fundos...",
                }
            ),
            "neighborhood": forms.TextInput(
                attrs={
                    "placeholder": "Bairro",
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "placeholder": "Cidade",
                }
            ),
            "state": forms.TextInput(
                attrs={
                    "placeholder": "SP",
                    "maxlength": "2",
                }
            ),
            "reference": forms.TextInput(
                attrs={
                    "placeholder": "Ex.: Próximo ao mercado",
                }
            ),
        }

    def clean_zip_code(self):
        zip_code = self.cleaned_data["zip_code"]

        digits = "".join(
            char for char in zip_code
            if char.isdigit()
        )

        if len(digits) != 8:
            raise forms.ValidationError(
                "Informe um CEP válido."
            )

        return f"{digits[:5]}-{digits[5:]}"

    def clean_state(self):
        state = self.cleaned_data["state"].strip().upper()

        if len(state) != 2:
            raise forms.ValidationError(
                "Informe a sigla do estado com 2 letras."
            )

        return state
