import hashlib
import uuid
from datetime import timedelta
from unittest.mock import patch
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.utils import timezone
from .base import CriticalTestCase
from apps.billing.models import (
    Subscription,
    Credit,
    Invoice,
    FiscalInvoice,
    FiscalSettings,
    TaxRate,
    MunicipalExport,
)
from apps.merchant.schema import fields_schema
from apps.superpanel.registry import RESOURCES
from apps.prospecting.models import (
    ProspectingBatch,
    ProspectingControl,
    ProspectingQueueItem,
    ProspectingSentPhone,
)


class ReactAdminParityTests(CriticalTestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="lvh.me")
        self.client.force_login(self.superuser)

    def test_all_global_lists_and_add_forms(self):
        for key in RESOURCES:
            with self.subTest(resource=key):
                response = self.client.get(f"/api/superadmin/resources/{key}/")
                self.assertEqual(response.status_code, 200, response.content[:300])
                if response.json()["can_add"]:
                    form = self.client.get(f"/api/superadmin/resources/{key}/new/")
                    self.assertEqual(form.status_code, 200, form.content[:300])

    def test_upload_types_preserve_backend_widget(self):
        class Upload(forms.Form):
            photo = forms.ImageField()
            csv = forms.FileField(
                widget=forms.ClearableFileInput(attrs={"accept": ".csv"})
            )
            other = forms.FileField()

        self.assertEqual(
            [f["accept"] for f in fields_schema(Upload())], ["image/*", ".csv", ""]
        )

    def credit_data(self, sub):
        return {
            "tenant_id": sub.tenant_id,
            "months": 2,
            "reason": "Cortesia de homologação",
            "token": str(uuid.uuid4()),
        }

    def test_credit_screen_links_to_free_days_for_same_tenant(self):
        sub, _ = Subscription.objects.get_or_create(tenant=self.tenant_a)
        response = self.client.get(
            f"/api/superadmin/subscriptions/{sub.pk}/credit/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["free_days_url"],
            f"/painel/tenants-tenant/{self.tenant_a.pk}/gratuidade",
        )

    def test_credit_preview_confirm_repeat_and_no_invoice(self):
        sub, _ = Subscription.objects.get_or_create(tenant=self.tenant_a)
        url = f"/api/superadmin/subscriptions/{sub.pk}/credit/"
        data = self.credit_data(sub)
        before = Invoice.objects.count()
        preview = self.client.post(url, data)
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(Credit.objects.filter(manual_token=data["token"]).exists())
        data["preview"] = preview.json()["preview"]
        first = self.client.post(url, data)
        second = self.client.post(url, data)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["valid_until"], second.json()["valid_until"])
        self.assertEqual(Credit.objects.filter(manual_token=data["token"]).count(), 1)
        self.assertEqual(Invoice.objects.count(), before)
        data["months"] = 3
        self.assertEqual(self.client.post(url, data).status_code, 409)

    def test_credit_requires_reason_and_refuses_stale_preview(self):
        sub, _ = Subscription.objects.get_or_create(tenant=self.tenant_a)
        url = f"/api/superadmin/subscriptions/{sub.pk}/credit/"
        data = self.credit_data(sub)
        self.assertEqual(
            self.client.post(url, {**data, "reason": " "}).status_code, 400
        )
        data["preview"] = self.client.post(url, data).json()["preview"]
        sub.valid_until = timezone.localdate() + timedelta(days=20)
        sub.save()
        self.assertEqual(self.client.post(url, data).status_code, 409)
        self.assertFalse(Credit.objects.filter(manual_token=data["token"]).exists())

    def note(self):
        invoice = Invoice.objects.create(
            tenant=self.tenant_a,
            plan_name="Mensal",
            months=1,
            amount=149,
            method="PIX",
            environment="sandbox",
            due_date=timezone.localdate(),
        )
        blob = b"%PDF-1.4 test fixture"
        return FiscalInvoice.objects.create(
            invoice=invoice,
            amount=149,
            status="AUTHORIZED",
            pdf_content=blob,
            pdf_sha256=hashlib.sha256(blob).hexdigest(),
        )

    def test_readonly_action_returns_real_csv_and_documents(self):
        note = self.note()
        url = "/api/superadmin/resources/billing-fiscalinvoice/"
        response = self.client.post(
            url + "actions/", {"action": "export_report", "ids": [note.pk]}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(self.tenant_a.name, response.content.decode("utf-8-sig"))
        download = self.client.get(f"{url}{note.pk}/download/pdf/")
        self.assertEqual(download.content, bytes(note.pdf_content))
        self.assertEqual(download["Content-Type"], "application/pdf")
        self.assertEqual(
            self.client.get(f"{url}{note.pk}/download/exe/").status_code, 404
        )
        self.client.logout()
        self.assertEqual(
            self.client.get(f"{url}{note.pk}/download/pdf/").status_code, 401
        )

    @patch("apps.billing.tasks.archive_and_send_nfse.delay")
    @patch("apps.billing.tasks.reconcile_fiscal_invoices.delay")
    def test_fiscal_readonly_actions_schedule_existing_tasks(self, reconcile, send):
        note = self.note()
        for action in ("consult", "resend_email"):
            response = self.client.post(
                "/api/superadmin/resources/billing-fiscalinvoice/actions/",
                {"action": action, "ids": [note.pk]},
            )
            self.assertEqual(response.status_code, 200, response.content)
        reconcile.assert_called_once()
        send.assert_called_once_with(note.pk)

    def test_municipal_upload_download_invalid_file(self):
        url = "/api/superadmin/resources/billing-municipalexport/"
        fields = self.client.get(url + "new/").json()["fields"]
        self.assertIn(
            ".csv", next(f for f in fields if f["name"] == "upload")["accept"]
        )
        data = {
            "month": str(timezone.localdate().replace(day=1)),
            "environment": "sandbox",
            "upload": SimpleUploadedFile("municipal.csv", b"original;municipal\n"),
        }
        response = self.client.post(url + "new/", data)
        self.assertEqual(response.status_code, 200, response.content)
        pk = response.json()["id"]
        download = self.client.get(f"{url}{pk}/download/csv/")
        self.assertEqual(download.content, b"original;municipal\n")
        data["upload"] = SimpleUploadedFile("image.png", b"not csv")
        self.assertEqual(self.client.post(url + "new/", data).status_code, 400)

    def test_tax_initials_and_dashboard_real_alert(self):
        config = FiscalSettings.objects.create(environment="sandbox")
        fields = self.client.get(
            "/api/superadmin/resources/billing-taxrate/new/"
        ).json()["fields"]
        self.assertEqual(
            str(next(f["value"] for f in fields if f["name"] == "configuration")),
            str(config.pk),
        )
        self.assertTrue(
            any(
                "ISS" in a["text"]
                for a in self.client.get("/api/superadmin/dashboard/").json()["alerts"]
            )
        )
        TaxRate.objects.create(
            configuration=config,
            month=timezone.localdate().replace(day=1),
            iss=2,
            checked_at=timezone.now(),
        )
        self.assertFalse(
            any(
                "ISS" in a["text"]
                for a in self.client.get("/api/superadmin/dashboard/").json()["alerts"]
            )
        )

    def test_prospecting_settings_pause_and_controlled_removal(self):
        url = "/api/superadmin/prospecting/"
        response = self.client.post(
            url,
            {
                "prospecting_action": "save_settings",
                "weekdays": ["0", "2"],
                "start_time": "09:00",
                "end_time": "18:00",
                "messages_per_minute": "2",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(ProspectingControl.current().weekday_numbers, {0, 2})
        self.assertTrue(
            self.client.post(url, {"prospecting_action": "start"}).json()[
                "confirmation_required"
            ]
        )
        self.client.post(url, {"prospecting_action": "start", "confirmed": "yes"})
        self.assertTrue(ProspectingControl.current().enabled)
        self.client.post(url, {"prospecting_action": "pause"})
        self.assertFalse(ProspectingControl.current().enabled)
        batch = ProspectingBatch.objects.create(filename="contacts.xlsx")
        ProspectingQueueItem.objects.create(
            batch=batch, phone="5511999999999", establishment="Teste"
        )
        ProspectingSentPhone.objects.create(phone="5511888888888")
        response = self.client.post(
            url,
            {
                "prospecting_action": "delete_batch",
                "batch_id": batch.pk,
                "confirmed": "yes",
            },
        )
        self.assertEqual(response.status_code, 200)
        batch.refresh_from_db()
        self.assertFalse(batch.is_active)
        self.assertFalse(batch.items.exists())
        self.assertTrue(ProspectingSentPhone.objects.exists())
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_prospecting_rejects_invalid_upload_and_configuration(self):
        url = "/api/superadmin/prospecting/"
        response = self.client.post(
            url,
            {
                "prospecting_action": "import",
                "prospecting_file": SimpleUploadedFile("bad.csv", b"bad"),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.post(url, {"prospecting_action": "save_settings"}).status_code,
            400,
        )

    def test_special_operations_host_role_and_csrf(self):
        paths = ["/api/superadmin/prospecting/", "/api/superadmin/evolution/"]
        for path in paths:
            for user, host, status in (
                (self.admin_a, "lvh.me", 403),
                (self.superuser, self.host(self.tenant_a), 404),
            ):
                client = Client(HTTP_HOST=host)
                client.force_login(user)
                self.assertEqual(client.get(path).status_code, status)
                self.assertEqual(client.post(path, {}).status_code, status)
            client = Client(HTTP_HOST="lvh.me", enforce_csrf_checks=True)
            client.force_login(self.superuser)
            self.assertEqual(client.post(path, {}).status_code, 403)

    @override_settings(LEGACY_ADMIN_ENABLED=False, MERCHANT_REACT_ENABLED=True)
    def test_legacy_superadmin_remains_available(self):
        self.assertEqual(self.client.get("/superadmin-legacy/").status_code, 200)

    def test_user_password_uses_admin_validation_and_masks_hash(self):
        detail = self.client.get(
            f"/api/superadmin/resources/accounts-user/{self.admin_a.pk}/"
        )
        self.assertNotIn(self.admin_a.password, detail.content.decode())
        url = f"/api/superadmin/users/{self.admin_a.pk}/password/"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(
            self.client.post(url, {"password1": "x", "password2": "y"}).status_code, 400
        )
        response = self.client.post(
            url,
            {
                "password1": "New-Strong-Test!2026",
                "password2": "New-Strong-Test!2026",
                "usable_password": "true",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.admin_a.refresh_from_db()
        self.assertTrue(self.admin_a.check_password("New-Strong-Test!2026"))

    def test_prospecting_import_uses_existing_xlsx_importer(self):
        from apps.prospecting.tests import XlsxFactoryMixin

        upload = XlsxFactoryMixin()._xlsx([("Loja Teste", "11999998888")])
        upload.name = "leads.xlsx"
        response = self.client.post(
            "/api/superadmin/prospecting/",
            {"prospecting_action": "import", "prospecting_file": upload},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(ProspectingBatch.objects.count(), 1)
        self.assertEqual(ProspectingQueueItem.objects.count(), 1)

    @override_settings(EVOLUTION_MONITOR_ENABLED=True)
    def test_evolution_adapter_uses_legacy_limits_and_qr(self):
        import base64
        from apps.integrations.models import WhatsAppIntegrationState

        row = WhatsAppIntegrationState.objects.create(
            identity="test",
            environment="sandbox",
            instance="platform",
            status="pairing",
            manual_required=True,
        )
        qr = (
            "data:image/png;base64,"
            + base64.b64encode(b"\x89PNG\r\n\x1a\ntest").decode()
        )
        with patch("apps.integrations.admin.enabled", return_value=True), patch(
            "apps.integrations.admin.current_state", return_value=row
        ), patch("apps.integrations.admin.request_action") as action, patch(
            "apps.integrations.admin.claim", return_value=(row.pk, "lease")
        ), patch(
            "apps.integrations.admin.release"
        ), patch(
            "apps.integrations.admin.EvolutionClient"
        ) as client:
            client.return_value.status.return_value = "close"
            client.return_value.connect.return_value = {"base64": qr}
            response = self.client.post(
                "/api/superadmin/evolution/", {"action": "pair"}
            )
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["qr"], qr)
            action.assert_called_once_with("pair", self.superuser)
            self.assertNotIn("lease_token", response.content.decode())
            from apps.integrations.whatsapp.client import EvolutionError

            action.side_effect = EvolutionError("rate_limit")
            response = self.client.post(
                "/api/superadmin/evolution/", {"action": "restart"}
            )
            self.assertTrue(
                any(m["level"] == "error" for m in response.json()["messages"])
            )
        self.assertEqual(
            self.client.post(
                "/api/superadmin/evolution/", {"action": "logout"}
            ).status_code,
            400,
        )

    def test_readonly_bulk_action_checks_each_object_and_invalid_ids(self):
        from apps.superpanel.registry import resource_admin

        note = self.note()
        url = "/api/superadmin/resources/billing-fiscalinvoice/actions/"
        admin = resource_admin("billing-fiscalinvoice")
        with patch.object(
            admin,
            "has_view_permission",
            side_effect=lambda request, obj=None: obj is None,
        ):
            self.assertEqual(
                self.client.post(
                    url, {"action": "export_report", "ids": [note.pk]}
                ).status_code,
                403,
            )
        self.assertEqual(
            self.client.post(
                url, {"action": "export_report", "ids": ["invalid"]}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                url, {"action": "export_report", "ids": [note.pk + 999]}
            ).status_code,
            404,
        )

    def test_xml_download_and_integrity_check(self):
        note = self.note()
        note.xml_content = b'<?xml version="1.0"?><nfse/>'
        note.xml_sha256 = hashlib.sha256(note.xml_content).hexdigest()
        note.save()
        url = f"/api/superadmin/resources/billing-fiscalinvoice/{note.pk}/download/xml/"
        result = self.client.get(url)
        self.assertEqual(result.content, bytes(note.xml_content))
        self.assertEqual(result["Content-Type"], "application/xml")
        note.xml_sha256 = "0" * 64
        note.save()
        self.assertEqual(self.client.get(url).status_code, 404)
