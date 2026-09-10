import io
import json
import zipfile
from datetime import datetime
from unittest.mock import patch
from urllib import error
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .evolution import (
    EvolutionDeliveryUnknownError,
    EvolutionInstanceUnavailableError,
    EvolutionNumberNotOnWhatsAppError,
    EvolutionReachoutRestrictedError,
    ensure_prospecting_instance_open,
    send_prospecting_text,
)
from .importer import import_prospecting_xlsx
from .message import build_prospecting_message
from .models import (
    ProspectingBatch,
    ProspectingControl,
    ProspectingQueueItem,
    ProspectingSentPhone,
)
from .phones import normalize_br_phone
from .tasks import MAX_CANDIDATES_PER_RUN, PROSPECTING_QUEUE, send_next_prospecting_message
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
        PROSPECTING_EVOLUTION_ACK_TIMEOUT=1,
    )
    @patch("apps.prospecting.evolution._request_json")
    def test_send_uses_canonical_jid_and_requires_server_ack(self, mocked_request):
        mocked_request.side_effect = [
            [
                {
                    "jid": "5515996325675@s.whatsapp.net",
                    "exists": True,
                    "number": "551596325675",
                }
            ],
            {
                "key": {
                    "id": "MSG-1",
                    "remoteJid": "5515996325675@s.whatsapp.net",
                },
                "status": "PENDING",
            },
            {
                "messages": {
                    "records": [
                        {
                            "key": {"id": "MSG-1"},
                            "status": "SERVER_ACK",
                            "MessageUpdate": [],
                        }
                    ]
                }
            },
        ]

        receipt = send_prospecting_text("551596325675", "Olá, Loja A!")

        self.assertEqual(receipt.message_id, "MSG-1")
        self.assertEqual(receipt.remote_jid, "5515996325675@s.whatsapp.net")
        self.assertEqual(
            mocked_request.call_args_list[1].args,
            (
                "POST",
                "message/sendText",
                {
                    "number": "5515996325675",
                    "text": "Olá, Loja A!",
                },
            ),
        )
        self.assertEqual(
            mocked_request.call_args_list[2].args,
            (
                "POST",
                "chat/findMessages",
                {"where": {"key": {"id": "MSG-1"}}},
            ),
        )

    @override_settings(
        EVOLUTION_API_URL="https://evolution.test",
        EVOLUTION_API_KEY="test-key",
        PROSPECTING_EVOLUTION_INSTANCE="prospecting",
        EVOLUTION_API_TIMEOUT=4,
        PROSPECTING_EVOLUTION_ACK_TIMEOUT=1,
    )
    @patch("apps.prospecting.evolution._request_json")
    def test_463_after_pending_is_not_classified_as_sent(self, mocked_request):
        mocked_request.side_effect = [
            [{"jid": "5511999999999@s.whatsapp.net", "exists": True, "number": "5511999999999"}],
            {
                "key": {"id": "MSG-463", "remoteJid": "5511999999999@s.whatsapp.net"},
                "status": "PENDING",
            },
            {
                "messages": {
                    "records": [
                        {
                            "key": {"id": "MSG-463"},
                            "status": "PENDING",
                            "MessageUpdate": [
                                {"status": 0, "messageStubParameters": ["463"]}
                            ],
                        }
                    ]
                }
            },
        ]

        with self.assertRaises(EvolutionReachoutRestrictedError):
            send_prospecting_text("5511999999999", "Olá!")

    @override_settings(
        EVOLUTION_API_URL="https://evolution.test",
        EVOLUTION_API_KEY="test-key",
        PROSPECTING_EVOLUTION_INSTANCE="prospecting",
        EVOLUTION_API_TIMEOUT=4,
    )
    @patch("apps.prospecting.evolution._request_json")
    def test_exists_false_is_classified_as_number_without_whatsapp(self, mocked_request):
        mocked_request.return_value = [
            {
                "jid": "5511999999999@s.whatsapp.net",
                "exists": False,
                "number": "5511999999999",
            }
        ]

        with self.assertRaises(EvolutionNumberNotOnWhatsAppError):
            send_prospecting_text("5511999999999", "Olá!")

    @override_settings(
        EVOLUTION_API_URL="https://evolution.test",
        EVOLUTION_API_KEY="test-key",
        PROSPECTING_EVOLUTION_INSTANCE="prospecting",
        PROSPECTING_EVOLUTION_AUTO_RECONNECT=True,
        PROSPECTING_EVOLUTION_RECONNECT_WAIT_SECONDS=2,
    )
    @patch("apps.prospecting.evolution.time.sleep", return_value=None)
    @patch("apps.prospecting.evolution._request_json")
    def test_closed_instance_is_restarted_and_rechecked(
        self, mocked_request, mocked_sleep
    ):
        mocked_request.side_effect = [
            {"instance": {"instanceName": "prospecting", "state": "close"}},
            {},
            {"instance": {"instanceName": "prospecting", "state": "open"}},
        ]

        self.assertEqual(ensure_prospecting_instance_open(), "reconnected")
        self.assertEqual(
            mocked_request.call_args_list[1].args,
            ("PUT", "instance/restart"),
        )
        mocked_sleep.assert_called()


class ProspectingPhoneTests(TestCase):
    def test_normalizes_brazilian_numbers(self):
        self.assertEqual(normalize_br_phone("(11) 99999-9999"), "5511999999999")
        self.assertEqual(normalize_br_phone("5511999999999"), "5511999999999")
        self.assertEqual(normalize_br_phone("11 3333-4444"), "551133334444")

    def test_rejects_invalid_phone(self):
        self.assertIsNone(normalize_br_phone("123"))
        self.assertIsNone(normalize_br_phone(""))


class ProspectingMessageTests(TestCase):
    def test_personalizes_store_name_and_offers_presentation_on_interest(self):
        text = build_prospecting_message("PADARIA REAL")
        self.assertIn("para a PADARIA REAL ter um site próprio", text)
        self.assertIn("como ele pode funcionar para a PADARIA REAL", text)
        self.assertIn("eu envio uma apresentação", text)
        self.assertNotIn("Estou enviando uma apresentação", text)
        self.assertNotIn("R$ 199", text)
        self.assertNotIn("por mês", text)
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
        self.assertEqual(batch.queued_contacts, 2)
        self.assertEqual(batch.skipped_contacted, 1)
        self.assertEqual(batch.skipped_duplicate, 1)
        self.assertEqual(batch.invalid_contacts, 1)
        self.assertTrue(batch.items.filter(phone="5511999999992").exists())
        self.assertTrue(batch.items.filter(phone="5511999999993").exists())
        self.assertEqual(batch.contacts.count(), 3)
        self.assertTrue(batch.contacts_index_complete)

    def test_second_upload_never_requeues_phone_already_contacted(self):
        first = import_prospecting_xlsx(self._xlsx([("Loja A", "11999999999")])).batch
        item = first.items.get()
        item.status = ProspectingQueueItem.Status.SENT
        item.save(update_fields=["status"])
        ProspectingSentPhone.objects.create(phone=item.phone)

        second = import_prospecting_xlsx(self._xlsx([("Loja A", "11999999999")])).batch
        self.assertEqual(second.queued_contacts, 0)
        self.assertEqual(second.skipped_contacted, 1)
        self.assertEqual(second.contacts.count(), 1)
        self.assertEqual(second.contacted_contacts, 1)


    def test_same_phone_can_wait_in_two_batches_without_losing_second_batch_membership(self):
        first = import_prospecting_xlsx(
            self._xlsx([("Loja A", "11999999991")]),
            filename="planilha-1.xlsx",
        ).batch
        second = import_prospecting_xlsx(
            self._xlsx([("Loja A repetida", "11999999991")]),
            filename="planilha-2.xlsx",
        ).batch

        self.assertEqual(first.items.count(), 1)
        self.assertEqual(second.items.count(), 1)
        self.assertEqual(first.contacts.count(), 1)
        self.assertEqual(second.contacts.count(), 1)
        self.assertEqual(second.skipped_duplicate, 0)


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
        self.connection_patcher = patch(
            "apps.prospecting.tasks.ensure_prospecting_instance_open",
            return_value="open",
        )
        self.mocked_connection = self.connection_patcher.start()
        self.addCleanup(self.connection_patcher.stop)

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

        self.assertIn("attempted=10", result)
        self.assertEqual(mocked_send.call_count, 10)
        self.assertEqual(self.batch.items.filter(status=ProspectingQueueItem.Status.SENT).count(), 10)
        self.assertEqual(self.batch.items.filter(status=ProspectingQueueItem.Status.PENDING).count(), 1)


    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_numbers_without_whatsapp_do_not_consume_per_minute_quota(self, mocked_send, mocked_allowed):
        mocked_send.side_effect = [
            EvolutionNumberNotOnWhatsAppError("sem whatsapp"),
            EvolutionNumberNotOnWhatsAppError("sem whatsapp"),
            None,
        ]
        first = self._queue("5511999999901", "Sem WhatsApp 1")
        second = self._queue("5511999999902", "Sem WhatsApp 2")
        sent = self._queue("5511999999903", "Loja válida")

        result = send_next_prospecting_message()

        self.assertIn("sent=1", result)
        self.assertIn("not_whatsapp=2", result)
        self.assertEqual(mocked_send.call_count, 3)
        self.assertFalse(ProspectingQueueItem.objects.filter(pk=first.pk).exists())
        self.assertFalse(ProspectingQueueItem.objects.filter(pk=second.pk).exists())
        sent.refresh_from_db()
        self.assertEqual(sent.status, ProspectingQueueItem.Status.SENT)
        self.assertTrue(ProspectingSentPhone.objects.filter(phone=sent.phone).exists())
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.failed_contacts, 2)

    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_scan_is_bounded_when_many_numbers_have_no_whatsapp(self, mocked_send, mocked_allowed):
        mocked_send.side_effect = EvolutionNumberNotOnWhatsAppError("sem whatsapp")
        for index in range(MAX_CANDIDATES_PER_RUN + 1):
            self._queue(f"5511988{index:06d}")

        result = send_next_prospecting_message()

        self.assertIn(f"attempted={MAX_CANDIDATES_PER_RUN}", result)
        self.assertIn(f"not_whatsapp={MAX_CANDIDATES_PER_RUN}", result)
        self.assertEqual(mocked_send.call_count, MAX_CANDIDATES_PER_RUN)
        self.assertEqual(
            self.batch.items.filter(status=ProspectingQueueItem.Status.PENDING).count(),
            1,
        )

    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_explicit_rejection_does_not_permanently_block_phone(self, mocked_send, mocked_allowed):
        from apps.prospecting.evolution import EvolutionRejectedError

        mocked_send.side_effect = EvolutionRejectedError("rejeitado")
        item = self._queue("5511999999997", "Loja rejeitada")

        self.assertEqual(send_next_prospecting_message(), "rejected")
        self.assertFalse(ProspectingSentPhone.objects.filter(phone=item.phone).exists())
        item.refresh_from_db()
        self.assertEqual(item.status, ProspectingQueueItem.Status.PENDING)
        self.assertIsNone(item.processed_at)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.failed_contacts, 0)

    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_463_pauses_prospecting_and_returns_lead_to_pending(
        self, mocked_send, mocked_allowed
    ):
        mocked_send.side_effect = EvolutionReachoutRestrictedError("463")
        item = self._queue("5511999999911", "Loja bloqueada pelo reachout")

        self.assertEqual(send_next_prospecting_message(), "reachout-restricted")

        self.control.refresh_from_db()
        item.refresh_from_db()
        self.assertFalse(self.control.enabled)
        self.assertEqual(item.status, ProspectingQueueItem.Status.PENDING)
        self.assertIsNone(item.processed_at)
        self.assertFalse(ProspectingSentPhone.objects.filter(phone=item.phone).exists())

    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_missing_ack_marks_unknown_and_pauses_without_duplicate_retry(
        self, mocked_send, mocked_allowed
    ):
        mocked_send.side_effect = EvolutionDeliveryUnknownError("sem ack")
        item = self._queue("5511999999912", "Loja ACK incerto")

        self.assertEqual(send_next_prospecting_message(), "unknown-delivery")

        self.control.refresh_from_db()
        item.refresh_from_db()
        self.assertFalse(self.control.enabled)
        self.assertEqual(item.status, ProspectingQueueItem.Status.UNKNOWN)
        self.assertTrue(ProspectingSentPhone.objects.filter(phone=item.phone).exists())

    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    def test_disconnected_instance_does_not_claim_any_lead(self, mocked_allowed):
        self.mocked_connection.side_effect = EvolutionInstanceUnavailableError("offline")
        item = self._queue("5511999999913", "Loja aguardando reconexão")

        self.assertEqual(send_next_prospecting_message(), "instance-unavailable")

        item.refresh_from_db()
        self.assertEqual(item.status, ProspectingQueueItem.Status.PENDING)
        self.assertFalse(ProspectingSentPhone.objects.filter(phone=item.phone).exists())

    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_processes_oldest_active_spreadsheet_first(self, mocked_send, mocked_allowed):
        first = self._queue("5511999999921", "Planilha 1")
        second_batch = ProspectingBatch.objects.create(
            filename="planilha-2.xlsx", total_contacts=1, queued_contacts=1
        )
        second = ProspectingQueueItem.objects.create(
            batch=second_batch, phone="5511999999922", establishment="Planilha 2"
        )

        self.assertEqual(send_next_prospecting_message(), "sent")

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, ProspectingQueueItem.Status.SENT)
        self.assertEqual(second.status, ProspectingQueueItem.Status.PENDING)
        mocked_send.assert_called_once_with(first.phone, build_prospecting_message(first.establishment))

    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_duplicate_phone_in_next_spreadsheet_is_skipped_and_next_lead_is_sent(
        self, mocked_send, mocked_allowed
    ):
        duplicated_phone = "5511999999931"
        first = self._queue(duplicated_phone, "Planilha 1")
        second_batch = ProspectingBatch.objects.create(
            filename="planilha-2.xlsx", total_contacts=2, queued_contacts=2
        )
        duplicate = ProspectingQueueItem.objects.create(
            batch=second_batch, phone=duplicated_phone, establishment="Repetida"
        )
        unique = ProspectingQueueItem.objects.create(
            batch=second_batch, phone="5511999999932", establishment="Nova"
        )

        self.assertEqual(send_next_prospecting_message(), "sent")
        self.assertFalse(ProspectingQueueItem.objects.filter(pk=duplicate.pk).exists())
        self.assertEqual(send_next_prospecting_message(), "sent")

        unique.refresh_from_db()
        self.assertEqual(unique.status, ProspectingQueueItem.Status.SENT)
        self.assertEqual(mocked_send.call_count, 2)
        self.assertTrue(ProspectingSentPhone.objects.filter(phone=first.phone).exists())

    @patch("apps.prospecting.models.ProspectingControl.is_allowed_at", return_value=True)
    @patch("apps.prospecting.tasks.send_prospecting_text")
    def test_removed_first_spreadsheet_allows_same_phone_from_second_to_continue(
        self, mocked_send, mocked_allowed
    ):
        phone = "5511999999940"
        first = self._queue(phone, "Planilha removida")
        second_batch = ProspectingBatch.objects.create(
            filename="planilha-2.xlsx", total_contacts=1, queued_contacts=1
        )
        second = ProspectingQueueItem.objects.create(
            batch=second_batch, phone=phone, establishment="Planilha 2"
        )

        self.batch.is_active = False
        self.batch.removed_at = timezone.now()
        self.batch.save(update_fields=["is_active", "removed_at"])
        first.delete()

        self.assertEqual(send_next_prospecting_message(), "sent")
        second.refresh_from_db()
        self.assertEqual(second.status, ProspectingQueueItem.Status.SENT)
        mocked_send.assert_called_once()

    def test_task_is_routed_to_dedicated_queue(self):
        self.assertEqual(PROSPECTING_QUEUE, "prospecting")
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["apps.prospecting.tasks.send_next_prospecting_message"]["queue"],
            "prospecting",
        )
        schedule = settings.CELERY_BEAT_SCHEDULE["prospecting-dispatch"]
        self.assertEqual(schedule["options"]["queue"], "prospecting")


class ProspectingAdminTests(XlsxFactoryMixin, TestCase):
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

    def test_board_reconciles_contacted_numbers_from_global_phone_history(self):
        batch = import_prospecting_xlsx(
            self._xlsx([("Loja A", "11999999941"), ("Loja B", "11999999942")]),
            filename="board.xlsx",
        ).batch
        ProspectingSentPhone.objects.create(phone="5511999999941")

        response = self.client.get(
            reverse("super_admin:prospecting_prospectingbatch_changelist"),
            HTTP_HOST="localhost",
        )

        board_batch = next(
            item for item in response.context["prospecting_board_batches"] if item.pk == batch.pk
        )
        self.assertEqual(board_batch.board_contacted, 1)
        self.assertEqual(board_batch.board_pending, 1)
        self.assertContains(response, "Planilhas carregadas")
        self.assertContains(response, "board.xlsx")
        self.assertContains(response, "Excluir")

    def test_delete_spreadsheet_removes_its_pending_queue_and_preserves_history(self):
        first = import_prospecting_xlsx(
            self._xlsx([("Planilha 1", "11999999951")]),
            filename="planilha-1.xlsx",
        ).batch
        second = import_prospecting_xlsx(
            self._xlsx([("Planilha 2", "11999999952")]),
            filename="planilha-2.xlsx",
        ).batch
        ProspectingSentPhone.objects.create(phone="5511999999959")

        response = self.client.post(
            reverse("super_admin:prospecting_prospectingbatch_changelist"),
            {"prospecting_action": "delete_batch", "batch_id": first.pk},
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertIsNotNone(first.removed_at)
        self.assertEqual(first.items.filter(status=ProspectingQueueItem.Status.PENDING).count(), 0)
        self.assertTrue(second.is_active)
        self.assertEqual(second.items.filter(status=ProspectingQueueItem.Status.PENDING).count(), 1)
        self.assertTrue(ProspectingSentPhone.objects.filter(phone="5511999999959").exists())

