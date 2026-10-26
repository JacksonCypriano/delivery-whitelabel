"""JSON presentation of existing Django forms; no business rules in the browser."""

import datetime
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.admin.utils import label_for_field, lookup_field
from django.db.models import Model
from django.utils import timezone
from django.utils.html import strip_tags


def value(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return v
    if isinstance(v, (str, int, float)):
        return v
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime.datetime):
        if timezone.is_aware(v):
            v = timezone.localtime(v)
        return v.isoformat()
    if isinstance(v, (datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [value(x) for x in v]
    return str(v)


def display(admin, obj, name):
    if name in {"password", "encrypted_api_key", "lease_token"}:
        return "Protegido"
    if obj is None or not obj.pk:
        return ""
    if getattr(admin.admin_site, "name", "") == "super_admin":
        label = obj._meta.label_lower
        if label == "billing.subscription" and name == "credit_link":
            return {
                "url": f"/painel/billing-subscription/{obj.pk}/credito",
                "label": "Acrescentar meses",
            }
        if label == "integrations.whatsappintegrationstate" and name == "panel_link":
            from apps.integrations.whatsapp.monitor import identity

            if obj.identity == identity():
                return {"url": "/painel/evolution", "label": "Abrir painel"}
        if label == "billing.fiscalinvoice" and name == "document_links":
            return {
                "links": [
                    {
                        "url": f"/api/superadmin/resources/billing-fiscalinvoice/{obj.pk}/download/{kind}/",
                        "label": kind.upper(),
                    }
                    for kind in ("pdf", "xml")
                    if getattr(obj, kind + "_sha256")
                ]
            }
        if label == "billing.municipalexport" and name == "download_link":
            return {
                "url": f"/api/superadmin/resources/billing-municipalexport/{obj.pk}/download/csv/",
                "label": "Baixar CSV municipal",
            }
    if name == "iss_warning" and obj._meta.label_lower == "billing.fiscalsettings":
        from apps.billing.fiscal import monthly_warning

        return {
            "text": monthly_warning(obj),
            "links": [
                {
                    "url": "/painel/billing-taxrate",
                    "label": "Conferir/cadastrar alíquota",
                }
            ],
        }
    if name == "fee_information":
        return {"url": "/painel/taxas", "label": "Consultar tarifas atuais do Asaas"}
    if name == "activation_url" and getattr(obj, "activation_url", ""):
        from urllib.parse import urlsplit

        url = obj.activation_url
        if urlsplit(url).scheme == "https":
            return {"url": url, "label": "Ativar conta Asaas"}
    if name == "thumbnail" and hasattr(obj, "get_primary_image"):
        url = obj.get_primary_image()
        return {"image": url, "label": str(obj)} if url else ""
    try:
        field, attr, result = lookup_field(name, obj, admin)
        if field is not None and field.choices:
            result = getattr(obj, "get_" + name + "_display")()
        if isinstance(result, Model):
            result = str(result)
        if hasattr(result, "url"):
            return {"url": result.url, "label": str(result)} if result else ""
        # Existing admin display helpers sometimes return markup. Never inject it.
        return (
            strip_tags(str(value(result)))
            if not isinstance(result, (bool, int, float))
            else result
        )
    except (AttributeError, ValueError):
        return ""


def fields_schema(form, lookup=None):
    result = []
    for name, f in form.fields.items():
        bound = form[name]
        widget = f.widget
        kind = "text"
        if isinstance(f, forms.BooleanField):
            kind = "checkbox"
        elif isinstance(f, forms.FileField):
            kind = "file"
        elif isinstance(f, (forms.MultipleChoiceField, forms.ModelMultipleChoiceField)):
            kind = "multiple"
        elif isinstance(f, (forms.ChoiceField, forms.ModelChoiceField)):
            kind = "select"
        elif isinstance(f, (forms.DateTimeField, forms.SplitDateTimeField)):
            kind = "datetime-local"
        elif isinstance(f, forms.DateField):
            kind = "date"
        elif isinstance(f, forms.TimeField):
            kind = "time"
        elif isinstance(f, forms.EmailField):
            kind = "email"
        elif isinstance(widget, forms.Textarea):
            kind = "textarea"
        elif isinstance(widget, forms.PasswordInput):
            kind = "password"
        elif isinstance(f, forms.DecimalField):
            kind = "decimal"
        elif isinstance(f, forms.IntegerField):
            kind = "number"
        if isinstance(widget, forms.CheckboxSelectMultiple):
            kind = "checkboxes"
        if widget.is_hidden and name != "terms_accepted":
            kind = "hidden"
        current = "" if isinstance(widget, forms.PasswordInput) else bound.value()
        from django.contrib.auth.forms import ReadOnlyPasswordHashField

        if isinstance(f, ReadOnlyPasswordHashField):
            current = "Senha protegida. Use a operação Alterar senha."
            kind = "text"
        if isinstance(f, forms.BooleanField):
            current = f.to_python(current)
        if isinstance(f, forms.SplitDateTimeField) and isinstance(
            current, datetime.datetime
        ):
            current = value(current)[:16]
        if isinstance(f, forms.FileField):
            current = (
                {"url": current.url, "label": str(current)}
                if current and hasattr(current, "url")
                else None
            )
        elif isinstance(current, datetime.datetime):
            current = value(current)[:16]
        elif isinstance(current, datetime.time):
            current = current.strftime("%H:%M")
        elif isinstance(f, forms.DecimalField) and current is not None:
            current = str(current).replace(".", ",") if f.localize else str(current)
        choices = []
        relation = (
            lookup
            and isinstance(f, (forms.ModelChoiceField, forms.ModelMultipleChoiceField))
            and kind != "hidden"
        )
        if relation:
            kind = "relationship"
            selected = current if isinstance(current, (list, tuple)) else [current]
            selected = [x for x in selected if x not in (None, "")]
            try:
                choices = (
                    [
                        {
                            "value": str(f.prepare_value(x)),
                            "label": f.label_from_instance(x),
                        }
                        for x in f.queryset.filter(
                            **{(f.to_field_name or "pk") + "__in": selected}
                        )
                    ]
                    if selected
                    else []
                )
            except (ValueError, TypeError, ValidationError):
                choices = []
        if kind in ("select", "multiple", "checkboxes"):
            for k, label in f.choices:
                if isinstance(label, (tuple, list)):
                    choices.extend(
                        [{"value": str(a), "label": str(b)} for a, b in label]
                    )
                else:
                    choices.append(
                        {
                            "value": str(k),
                            "label": "Selecione…" if str(k) == "" else str(label),
                        }
                    )
        result.append(
            {
                "name": name,
                "html_name": bound.html_name,
                "label": str(f.label or name),
                "kind": kind,
                "lookup": lookup + "&field=" + name if relation else None,
                "multiple": isinstance(f, forms.ModelMultipleChoiceField),
                "accept": (
                    "image/*"
                    if isinstance(f, forms.ImageField)
                    else str(widget.attrs.get("accept", ""))
                ),
                "value": value(current),
                "required": f.required and not form.empty_permitted,
                "disabled": f.disabled or isinstance(f, ReadOnlyPasswordHashField),
                "help": strip_tags(str(f.help_text)),
                "choices": choices,
                "max_length": getattr(f, "max_length", None),
                "min": value(getattr(f, "min_value", None)),
                "max": value(getattr(f, "max_value", None)),
                "placeholder": str(widget.attrs.get("placeholder", "")),
                "split": isinstance(f, forms.SplitDateTimeField),
                "localized": f.localize,
                "errors": list(bound.errors),
            }
        )
    return result


def sections(admin, request, obj):
    return [
        {
            "title": str(title or "Informações"),
            "description": strip_tags(str(options.get("description", ""))),
            "fields": [
                x
                for row in options["fields"]
                for x in (row if isinstance(row, (list, tuple)) else [row])
            ],
        }
        for title, options in admin.get_fieldsets(request, obj)
    ]


def readonly(admin, request, obj):
    return [
        {
            "name": name,
            "label": str(label_for_field(name, admin.model, admin)),
            "value": display(admin, obj, name),
        }
        for name in admin.get_readonly_fields(request, obj)
    ]
