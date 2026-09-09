import io
import json
import zipfile
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .evolution import send_prospecting_text
from .importer import import_prospecting_xlsx
from .message import build_prospecting_message
from .models import ProspectingBatch, ProspectingControl, ProspectingQueueItem, ProspectingSentPhone
from .phones import normalize_br_phone
from .tasks import PROSPECTING_QUEUE, send_next_prospecting_message
from .xlsx_reader import read_prospecting_rows


class XlsxFactoryMixin:
    def _xlsx(self, rows, headers=("Nome da loja", "WhatsApp")):
        values = list(headers)
        for name, phone in rows:
            values.extend([name, phone])

        shared_items = "".join(f"<si><t>{value}</t></si>" for value in values)
        shared = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'count="{len(values)}" uniqueCount="{len(values)}">{shared_items}</sst>'
        )
        workbook = """<?xml version="1.0" encoding="UTF-8"?>
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Leads" sheetId="1" r:id="rId1"/></sheets>
        </workbook>"""
        rels = """<?xml version="1.0" encoding="UTF-8"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
        </Relationships>"""

        sheet_rows = ['<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>']
        shared_index = 2
        for row_num, _ in enumerate(rows, start=2):
            sheet_rows.append(
                f'<row r="{row_num}"><c r="A{row_num}" t="s"><v>{shared_index}</v></c>'
                f'<c r="B{row_num}" t="s"><v>{shared_index + 1}</v></c></row>'
            )
            shared_index += 2
        sheet = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + "".join(sheet_rows)
            + "</sheetData></worksheet>"
        )

        bio = io.BytesIO()
        bio.name = "leads.xlsx"
        with zipfile.ZipFile(bio, "w") as zf:
            zf.writestr("xl/workbook.xml", workbook)
            zf.writestr("xl/_rels/workbook.xml.rels", rels)
            zf.writestr("xl/worksheets/sheet1.xml", sheet)
            zf.writestr("xl/sharedStrings.xml", shared)
        bio.seek(0)
        return bio




class ProspectingEvolutionTests(TestCase):
    @override_settings(
        EVOLUTION_API_URL="https://evolution.test",
        EVOLUTION_API_KEY="test-key",
        PROSPECTING_EVOLUTION_INSTANCE="prospecting",
        EVOLUTION_API_TIMEOUT=4,
    )
    @patch("apps.prospecting.evolution.request.urlopen")
    def test_send_text_uses_current_evolution_payload_contract(self, mocked_urlopen):
        response = mocked_urlopen.return_value.__enter__.return_value
        response.status = 201

        send_prospecting_text("5511999999999", "Olá, Loja A!")

        request_obj = mocked_urlopen.call_args.args[0]
        payload = json.loads(request_obj.data.decode("utf-8"))

        self.assertEqual(
            payload,
            {
                "number": "5511999999999",
                "text": "Olá, Loja A!",
            },
        )
        self.assertNotIn("textMessage", payload)
        self.assertEqual(
            request_obj.full_url,
            "https://evolution.test/message/sendText/prospecting",
        )

class ProspectingPhoneTests(TestCase):
    def test_normalizes_brazilian_numbers(self):
        self.assertEqual(normalize_br_phone("(11) 99999-9999"), "5511999999999")
        self.assertEqual(normalize_br_phone("5511999999999"), "5511999999999")
        self.assertEqual(normalize_br_phone("11 3333-4444"), "551133334444")

    def test_rejects_invalid_phone(self):
        self.assertIsNone(normalize_br_phone("123"))
        self.assertIsNone(normalize_br_phone(""))


class ProspectingMessageTests(TestCase):
    def test_personalizes_store_name(self):
        text = build_prospecting_message("PADARIA REAL")
        self.assertIn("para a PADARIA REAL ter um site próprio", text)
        self.assertIn("colocar a PADARIA REAL no VemDeDelivery", text)
        self.assertIn("CNPJ 59.198.345/0001-44", text)


class ProspectingImportTests(XlsxFactoryMixin, TestCase):
    def test_reads_new_headers_and_legacy_establishment_header(self):
        rows = [("Loja A", "11999999999")]
        self.assertEqual(read_prospecting_rows(self._xlsx(rows)), rows)
        self.assertEqual(
            read_prospecting_rows(self._xlsx(rows, headers=("Estabelecimento", "WhatsApp"))),
            rows,
        )

    def test_batch_tracks_total_queue_duplicates_and_already_contacted(self):
        ProspectingSentPhone.objects.create(phone="5511999999991")
        existing_batch = ProspectingBatch.objects.create(filename="old.xlsx")
        ProspectingQueueItem.objects.create(
            batch=existing_batch,
            phone="5511999999992",
            establishment="Fila anterior",
        )
        xlsx = self._xlsx(
            [
                ("Já contatada", "11999999991"),
                ("Já na fila", "11999999992"),
                ("Nova", "11999999993"),
                ("Nova duplicada", "11999999993"),
                ("Inválida", "123"),
            ]
        )

        result = import_prospecting_xlsx(xlsx)
        batch = result.batch

        self.assertEqual(batch.total_contacts, 5)
        self.assertEqual(batch.queued_contacts, 1)
        self.assertEqual(batch.skipped_contacted, 1)
        self.assertEqual(batch.skipped_duplicate, 2)
        self.assertEqual(batch.invalid_contacts, 1)
        self.assertTrue(batch.items.filter(phone="5511999999993").exists())

    def test_second_upload_never_requeues_phone_already_contacted(self):
        first = import_prospecting_xlsx(self._xlsx([("Loja A", "11999999999")])).batch
        item = first.items.get()
        item.status = ProspectingQueueItem.Status.SENT
        item.save(update_fields=["status"])
        ProspectingSentPhone.objects.create(phone=item.phone)

        second = import_prospecting_xlsx(self._xlsx([("Loja A", "11999999999")])).batch
        self.assertEqual(second.queued_contacts, 0)
        self.assertEqual(second.skipped_contacted, 1)


class ProspectingControlTests(TestCase):
    def test_default_schedule_allows_weekday_between_09_and_21(self):
        control = ProspectingControl.current()
        control.enabled = True
        control.save(update_fields=["enabled"])
        moment = datetime(2026, 9, 8, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.assertTrue(control.is_allowed_at(moment))

    def test_default_schedule_blocks_at_21_00(self):
        control = ProspectingControl.current()
        control.enabled = True
        control.save(update_fields=["enabled"])
        moment = datetime(2026, 9, 8, 21, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.assertFalse(control.is_allowed_at(moment))

    def test_default_schedule_blocks_weekend(self):
        control = ProspectingControl.current()
        control.enabled = True
        control.save(update_fields=["enabled"])
        moment = datetime(2026, 9, 12, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.assertFalse(control.is_allowed_at(moment))


class ProspectingTaskTests(TestCase):
    def setUp(self):
        self.control = ProspectingControl.current()
        self.control.enabled = True
        self.control.messages_per_minute = 1
        self.control.save(update_fields=["enabled", "messages_per_minute"])
        self.batch = ProspectingBatch.objects.create(filename="task.xlsx", total_contacts=20, queued_contacts=20)

    def _queue(self, phone, name="Loja"):
        return ProspectingQueueItem.objects.create(batch=self.batch, phone=phone, establishment=name)

    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_sends_once_updates_batch_and_persists_phone_lock(self, mocked_send, mocked_allowed):
        item = self._queue("5511999999999", "Loja A")
        result = send_next_prospecting_message()
        self.assertEqual(result, "sent")
        mocked_send.assert_called_once()
        self.assertTrue(ProspectingSentPhone.objects.filter(phone=item.phone).exists())
        item.refresh_from_db()
        self.assertEqual(item.status, ProspectingQueueItem.Status.SENT)
        self.assertEqual(self.batch.contacted_contacts, 1)

    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=False)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_pause_or_window_does_not_consume_queue(self, mocked_send, mocked_allowed):
        item = self._queue("5511999999998")
        self.assertEqual(send_next_prospecting_message(), "outside-window")
        item.refresh_from_db()
        self.assertEqual(item.status, ProspectingQueueItem.Status.PENDING)
        mocked_send.assert_not_called()

    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_respects_configurable_ten_per_minute_limit(self, mocked_send, mocked_allowed):
        self.control.messages_per_minute = 10
        self.control.save(update_fields=["messages_per_minute"])
        for index in range(11):
            self._queue(f"551199999{index:04d}")

        result = send_next_prospecting_message()

        self.assertIn("processed=10", result)
        self.assertEqual(mocked_send.call_count, 10)
        self.assertEqual(self.batch.items.filter(status=ProspectingQueueItem.Status.SENT).count(), 10)
        self.assertEqual(self.batch.items.filter(status=ProspectingQueueItem.Status.PENDING).count(), 1)


    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_explicit_rejection_does_not_permanently_block_phone(self, mocked_send, mocked_allowed):
        from apps.prospecting.evolution import EvolutionRejectedError

        mocked_send.side_effect = EvolutionRejectedError("rejeitado")
        item = self._queue("5511999999997", "Loja rejeitada")

        self.assertEqual(send_next_prospecting_message(), "rejected")
        self.assertFalse(ProspectingSentPhone.objects.filter(phone=item.phone).exists())
        self.assertFalse(ProspectingQueueItem.objects.filter(phone=item.phone).exists())
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.failed_contacts, 1)

    def test_task_is_routed_to_dedicated_queue(self):
        self.assertEqual(PROSPECTING_QUEUE, "prospecting")
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["apps.prospecting.tasks.send_next_prospecting_message"]["queue"],
            "prospecting",
        )
        schedule = settings.CELERY_BEAT_SCHEDULE["prospecting-dispatch"]
        self.assertEqual(schedule["options"]["queue"], "prospecting")


class ProspectingAdminTests(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="prospecting-admin",
            email="prospecting-admin@example.com",
            password="test",
        )
        self.client.force_login(self.superuser)


    def test_sent_phone_lock_is_not_exposed_as_separate_superadmin_screen(self):
        from apps.tenants.admin_site import super_admin_site

        self.assertNotIn(ProspectingSentPhone, super_admin_site._registry)

    def test_operational_panel_renders_even_without_batches(self):
        response = self.client.get(
            reverse("super_admin:prospecting_prospectingbatch_changelist"),
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Importar nova planilha")
        self.assertContains(response, "Iniciar envios")
        self.assertContains(response, "Horário e velocidade")
        self.assertContains(response, "Fila Celery dedicada")
        self.assertContains(response, "Pendentes na fila")
