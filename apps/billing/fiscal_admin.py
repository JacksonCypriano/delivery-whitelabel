import csv
import hashlib
from pathlib import Path
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse, path
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html
from apps.tenants.admin_site import super_admin_site
from .admin import GlobalAdmin, ReadOnlyAdmin
from .models import (
    FiscalSettings,
    TaxRate,
    FiscalInvoice,
    FiscalCustomerRule,
    MunicipalExport,
)
from .fiscal_documents import attachment_response, LIMIT
from .fiscal import monthly_warning


@admin.register(FiscalSettings, site=super_admin_site)
class FiscalSettingsAdmin(GlobalAdmin):
    list_display = ["environment", "enabled", "iss_warning"]
    readonly_fields = ["iss_warning"]
    fields = [
        "environment",
        "enabled",
        "start_at",
        "iss_warning",
        "service_id",
        "service_code",
        "service_name",
        "description",
    ]

    def get_readonly_fields(self, request, obj=None):
        return ["iss_warning", "environment"] if obj else ["iss_warning"]

    @admin.display(description="Conferência mensal obrigatória do ISS")
    def iss_warning(self, obj):
        if not obj or not obj.pk:
            return "Salve a configuração e cadastre a alíquota mensal conferida na Contabilizei."
        return format_html(
            '<div role="alert" style="padding:14px;border:1px solid #b45309;border-radius:8px;background:#fffbeb;color:#78350f">{} <a style="text-decoration:underline" href="{}">Conferir/cadastrar alíquota</a></div>',
            monthly_warning(obj),
            reverse("super_admin:billing_taxrate_changelist"),
        )


@admin.register(TaxRate, site=super_admin_site)
class TaxRateAdmin(GlobalAdmin):
    list_display = ["configuration", "month", "iss", "checked_at", "checked_by"]
    list_filter = ["configuration", "month"]
    readonly_fields = ["warning", "checked_at", "checked_by"]
    fields = ["configuration", "month", "warning", "iss", "checked_at", "checked_by"]

    @admin.display(description="Lembrete de verificação")
    def warning(self, obj):
        return format_html(
            '<div role="alert" style="padding:14px;background:#fffbeb;color:#78350f;border:1px solid #b45309;border-radius:8px">{}</div>',
            "ATENÇÃO: confira o ISS no início de CADA MÊS em Contabilizei → Minhas Rotinas → Ver minhas alíquotas, mesmo que não mude. Não é a alíquota total do Simples. Salvar registra sua conferência. Confira também sempre que a contabilidade comunicar alteração.",
        )

    def save_model(self, request, obj, form, change):
        obj.checked_at = timezone.now()
        obj.checked_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(FiscalInvoice, site=super_admin_site)
class FiscalInvoiceAdmin(ReadOnlyAdmin):
    list_display = [
        "invoice",
        "status",
        "effective_date",
        "amount",
        "iss",
        "review_required",
        "notice",
        "document_links",
        "delivery_status",
        "delivery_notice",
    ]
    list_filter = [
        "invoice__environment",
        "status",
        "review_required",
        "effective_date",
    ]
    list_filter = list_filter + ["delivery_status"]
    search_fields = ["invoice__tenant__name", "number", "provider_id"]
    actions = ["consult", "export_report", "resend_email"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .defer("pdf_content", "xml_content")
            .select_related("invoice__tenant")
        )

    def get_readonly_fields(self, request, obj=None):
        return [
            f.name
            for f in self.model._meta.fields
            if f.name not in ("pdf_content", "xml_content")
        ] + ["document_links"]

    @admin.display(description="Documentos arquivados")
    def document_links(self, obj):
        from django.utils.html import format_html_join

        return (
            format_html_join(
                " · ",
                '<a href="{}">{}</a>',
                [
                    (
                        reverse(
                            "super_admin:billing_nfse_download", args=[obj.pk, kind]
                        ),
                        kind.upper(),
                    )
                    for kind in ("pdf", "xml")
                    if getattr(obj, kind + "_sha256")
                ],
            )
            or "Aguardando arquivo"
        )

    def get_urls(self):
        return [
            path(
                "<int:pk>/documento/<str:kind>/",
                self.admin_site.admin_view(self.download),
                name="billing_nfse_download",
            )
        ] + super().get_urls()

    def download(self, request, pk, kind):
        if not request.user.is_superuser or not request.user.is_active:
            raise PermissionDenied
        if kind not in ("pdf", "xml") or request.method != "GET":
            raise Http404
        note = get_object_or_404(FiscalInvoice, pk=pk)
        return attachment_response(
            getattr(note, kind + "_content"),
            getattr(note, kind + "_sha256"),
            f"nfse-{pk}.{kind}",
            "application/pdf" if kind == "pdf" else "application/xml",
        )

    @admin.action(
        description="Solicitar REENVIO do e-mail (confira o SMTP: pode duplicar mensagem)",
        permissions=["view"],
    )
    def resend_email(self, request, queryset):
        if not request.user.is_superuser:
            raise PermissionDenied
        from .tasks import archive_and_send_nfse
        from datetime import timedelta

        for pk in queryset.values_list("pk", flat=True)[:50]:
            with transaction.atomic():
                note = FiscalInvoice.objects.select_for_update().get(pk=pk)
                if note.status != "AUTHORIZED":
                    continue
                if note.delivery_status == "SENDING" and (
                    not note.delivery_checked_at
                    or note.delivery_checked_at > timezone.now() - timedelta(minutes=15)
                ):
                    continue
                note.delivery_status = "PENDING"
                note.delivery_notice = "Reenvio solicitado pelo superadmin."
                note.save(update_fields=["delivery_status", "delivery_notice"])
                self.log_change(
                    request, note, "Solicitado reenvio manual da nota por e-mail."
                )
            try:
                archive_and_send_nfse.delay(pk)
            except Exception:
                pass
        self.message_user(
            request,
            "Solicitações registradas; a fila periódica também recupera os envios pendentes.",
        )

    @admin.action(
        description="Consultar/reprocessar fila fiscal sem duplicação",
        permissions=["view"],
    )
    def consult(self, request, queryset):
        if not request.user.is_superuser:
            raise PermissionDenied
        from .tasks import reconcile_fiscal_invoices

        try:
            reconcile_fiscal_invoices.delay()
            self.message_user(
                request,
                "Conciliação fiscal solicitada. Erros de emissão devem ser corrigidos no Asaas; não será criada uma segunda nota.",
                messages.INFO,
            )
        except Exception:
            self.message_user(
                request,
                "Worker indisponível. A rotina periódica retomará a fila fiscal.",
                messages.WARNING,
            )

    @admin.action(
        description="Exportar relatório de conferência (não é CSV da prefeitura)",
        permissions=["view"],
    )
    def export_report(self, request, queryset):
        if not request.user.is_superuser:
            raise PermissionDenied
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="conferencia-nfse.csv"'
        response.write("\ufeff")
        writer = csv.writer(response, delimiter=";")
        writer.writerow(
            [
                "Loja",
                "Ambiente",
                "Cobrança",
                "NFS-e",
                "Competência",
                "Valor",
                "ISS (%)",
                "Situação",
                "Revisão fiscal",
            ]
        )

        def safe(value):
            text = str(value or "")
            return (
                "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
            )

        for note in queryset.select_related("invoice__tenant").iterator():
            writer.writerow(
                [
                    safe(v)
                    for v in [
                        note.invoice.tenant.name,
                        note.invoice.environment,
                        note.invoice_id,
                        note.number,
                        note.effective_date,
                        note.amount,
                        note.iss,
                        note.get_status_display(),
                        note.review_required,
                    ]
                ]
            )
        return response


@admin.register(FiscalCustomerRule, site=super_admin_site)
class FiscalCustomerRuleAdmin(GlobalAdmin):
    list_display = ["customer", "retain_iss", "hold", "reason"]


class MunicipalExportForm(forms.ModelForm):
    upload = forms.FileField(
        label="CSV V.004 ORIGINAL exportado da prefeitura",
        help_text="Arquivo mensal para importação na Contabilizei. Não envie o relatório genérico do sistema. Máximo 5 MB; não é disponibilizado aos lojistas.",
    )

    class Meta:
        model = MunicipalExport
        fields = ["month", "environment"]

    def clean_upload(self):
        upload = self.cleaned_data["upload"]
        if not upload.name.lower().endswith(".csv") or not 0 < upload.size <= LIMIT:
            raise forms.ValidationError("Envie um CSV de até 5 MB.")
        return upload

    def clean_month(self):
        month = self.cleaned_data["month"]
        if month.day != 1:
            raise forms.ValidationError("Informe o primeiro dia da competência.")
        return month


@admin.register(MunicipalExport, site=super_admin_site)
class MunicipalExportAdmin(GlobalAdmin):
    form = MunicipalExportForm
    list_display = ["month", "environment", "filename", "uploaded_at", "download_link"]
    list_filter = ["environment", "month"]

    def has_change_permission(self, request, obj=None):
        return False

    def get_fields(self, request, obj=None):
        return (
            [
                "month",
                "environment",
                "filename",
                "sha256",
                "uploaded_at",
                "download_link",
            ]
            if obj
            else ["month", "environment", "upload"]
        )

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj else []

    def get_queryset(self, request):
        return super().get_queryset(request).defer("content")

    def save_model(self, request, obj, form, change):
        blob = form.cleaned_data["upload"].read(LIMIT + 1)
        if len(blob) > LIMIT:
            raise PermissionDenied
        obj.content = blob
        obj.sha256 = hashlib.sha256(blob).hexdigest()
        obj.filename = Path(form.cleaned_data["upload"].name).name[:200]
        super().save_model(request, obj, form, change)

    @admin.display(description="CSV original para Contabilizei")
    def download_link(self, obj):
        return format_html(
            '<a href="{}">Baixar CSV municipal</a>',
            reverse("super_admin:billing_csv_download", args=[obj.pk]),
        )

    def get_urls(self):
        return [
            path(
                "<int:pk>/arquivo/",
                self.admin_site.admin_view(self.download),
                name="billing_csv_download",
            )
        ] + super().get_urls()

    def download(self, request, pk):
        if not request.user.is_superuser or not request.user.is_active:
            raise PermissionDenied
        if request.method != "GET":
            raise Http404
        obj = get_object_or_404(MunicipalExport, pk=pk)
        return attachment_response(
            obj.content,
            obj.sha256,
            f"prefeitura-{obj.month:%Y-%m}-{obj.pk}.csv",
            "text/csv",
        )
