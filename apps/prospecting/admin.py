from django.contrib import admin, messages
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.dateparse import parse_time

try:
    from unfold.admin import ModelAdmin
except ImportError:  # pragma: no cover
    ModelAdmin = admin.ModelAdmin

from apps.tenants.admin_site import super_admin_site

from .importer import import_prospecting_xlsx
from .models import ProspectingBatch, ProspectingControl, ProspectingQueueItem, ProspectingSentPhone
from .xlsx_reader import ProspectingSpreadsheetError


WEEKDAY_LABELS = (
    (0, "Segunda"),
    (1, "Terça"),
    (2, "Quarta"),
    (3, "Quinta"),
    (4, "Sexta"),
    (5, "Sábado"),
    (6, "Domingo"),
)


class ProspectingBatchAdmin(ModelAdmin):
    change_list_template = "admin/prospecting/prospectingbatch/change_list.html"
    list_display = (
        "filename",
        "created_at",
        "total_contacts",
        "queued_contacts",
        "contacted_display",
        "pending_display",
        "skipped_display",
        "issues_display",
    )
    ordering = ("-created_at", "-id")
    list_per_page = 25
    search_fields = ("filename",)

    def has_module_permission(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            contacted_count=Count("items", filter=Q(items__status=ProspectingQueueItem.Status.SENT)),
            pending_count=Count(
                "items",
                filter=Q(
                    items__status__in=(
                        ProspectingQueueItem.Status.PENDING,
                        ProspectingQueueItem.Status.PROCESSING,
                    )
                ),
            ),
            unknown_count=Count("items", filter=Q(items__status=ProspectingQueueItem.Status.UNKNOWN)),
        )

    @admin.display(description="Contatados", ordering="contacted_count")
    def contacted_display(self, obj):
        return obj.contacted_count

    @admin.display(description="Pendentes", ordering="pending_count")
    def pending_display(self, obj):
        return obj.pending_count

    @admin.display(description="Ignorados")
    def skipped_display(self, obj):
        return obj.skipped_contacted + obj.skipped_duplicate + obj.invalid_contacts

    @admin.display(description="Falhas/incertos")
    def issues_display(self, obj):
        return obj.failed_contacts + obj.unknown_count

    def _save_settings(self, request, control):
        start_time = parse_time(request.POST.get("start_time", ""))
        end_time = parse_time(request.POST.get("end_time", ""))
        weekdays_raw = request.POST.getlist("weekdays")

        try:
            messages_per_minute = int(request.POST.get("messages_per_minute", "1"))
        except (TypeError, ValueError):
            messages_per_minute = 0

        weekdays = sorted(
            {
                int(value)
                for value in weekdays_raw
                if value.isdigit() and 0 <= int(value) <= 6
            }
        )

        errors = []
        if start_time is None or end_time is None:
            errors.append("Informe horários inicial e final válidos.")
        elif start_time == end_time:
            errors.append("O horário inicial e o horário final precisam ser diferentes.")
        if not 1 <= messages_per_minute <= 10:
            errors.append("Contatos por minuto deve ficar entre 1 e 10.")
        if not weekdays:
            errors.append("Selecione pelo menos um dia da semana.")

        if errors:
            for error_message in errors:
                self.message_user(request, error_message, level=messages.ERROR)
            return False

        control.start_time = start_time
        control.end_time = end_time
        control.messages_per_minute = messages_per_minute
        control.weekdays = ",".join(str(value) for value in weekdays)
        control.save(update_fields=["start_time", "end_time", "messages_per_minute", "weekdays"])
        self.message_user(request, "Configuração de envio salva.", level=messages.SUCCESS)
        return True

    def changelist_view(self, request, extra_context=None):
        if not (request.user.is_active and request.user.is_superuser):
            return super().changelist_view(request, extra_context=extra_context)

        control = ProspectingControl.current()

        if request.method == "POST":
            action = request.POST.get("prospecting_action")

            if action == "import":
                upload = request.FILES.get("prospecting_file")
                if not upload:
                    self.message_user(request, "Selecione uma planilha XLSX.", level=messages.ERROR)
                elif not upload.name.lower().endswith(".xlsx"):
                    self.message_user(request, "O arquivo precisa ser .xlsx.", level=messages.ERROR)
                else:
                    try:
                        result = import_prospecting_xlsx(upload, filename=upload.name)
                    except ProspectingSpreadsheetError as exc:
                        self.message_user(request, str(exc), level=messages.ERROR)
                    else:
                        batch = result.batch
                        self.message_user(
                            request,
                            (
                                f"Planilha processada: {batch.total_contacts} contatos; "
                                f"{batch.queued_contacts} novos na fila; "
                                f"{batch.skipped_contacted} já contatados; "
                                f"{batch.skipped_duplicate} duplicados/na fila; "
                                f"{batch.invalid_contacts} inválidos."
                            ),
                            level=messages.SUCCESS,
                        )

            elif action == "save_settings":
                self._save_settings(request, control)

            elif action == "start":
                control.enabled = True
                control.save(update_fields=["enabled"])
                self.message_user(request, "Prospecção iniciada.", level=messages.SUCCESS)

            elif action == "pause":
                control.enabled = False
                control.save(update_fields=["enabled"])
                self.message_user(request, "Prospecção pausada.", level=messages.SUCCESS)

            return HttpResponseRedirect(request.path)

        pending_statuses = (ProspectingQueueItem.Status.PENDING, ProspectingQueueItem.Status.PROCESSING)
        latest_batch = self.get_queryset(request).first()
        context = {
            "prospecting_enabled": control.enabled,
            "prospecting_pending_count": ProspectingQueueItem.objects.filter(status__in=pending_statuses).count(),
            "prospecting_sent_count": ProspectingSentPhone.objects.count(),
            "prospecting_start_time": control.start_time.strftime("%H:%M"),
            "prospecting_end_time": control.end_time.strftime("%H:%M"),
            "prospecting_messages_per_minute": control.messages_per_minute,
            "prospecting_weekdays": control.weekday_numbers,
            "prospecting_weekday_labels": WEEKDAY_LABELS,
            "prospecting_timezone": timezone.get_current_timezone_name(),
            "prospecting_window_open": control.is_allowed_at(),
            "prospecting_latest_batch": latest_batch,
            "prospecting_queue_name": "prospecting",
        }
        if extra_context:
            context.update(extra_context)
        return super().changelist_view(request, extra_context=context)


super_admin_site.register(ProspectingBatch, ProspectingBatchAdmin)
