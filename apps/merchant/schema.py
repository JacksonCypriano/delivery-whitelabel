"""JSON presentation of existing Django forms; no business rules in the browser."""

import datetime
from decimal import Decimal
from django import forms
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
    if obj is None or not obj.pk:
        return ""
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


def fields_schema(form):
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
        if widget.is_hidden and name != "terms_accepted":
            kind = "hidden"
        current = bound.value()
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
        if kind in ("select", "multiple"):
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
                "value": value(current),
                "required": f.required and not form.empty_permitted,
                "disabled": f.disabled,
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
