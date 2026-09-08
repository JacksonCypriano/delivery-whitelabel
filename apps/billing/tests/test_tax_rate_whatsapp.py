from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import FiscalSettings, TaxRate, TaxRateWhatsAppReminder
from apps.billing.tasks import send_tax_rate_whatsapp_reminders
from apps.integrations.whatsapp.client import EvolutionError


@override_settings(
    BILLING_ENABLED=True,
    ASAAS_ENVIRONMENT="sandbox",
    ASAAS_API_KEY="test-only",
    ASAAS_WEBHOOK_TOKEN="testing-token-longer-than-thirty-two-characters",
    SUPERADMIN_PUBLIC_URL="https://homolog.vemdedelivery.example",
)
class TaxRateWhatsAppReminderTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_superuser(
            username="global-admin",
            email="admin@example.com",
            password="SenhaForte!2026",
            administrative_whatsapp="(11) 99999-9999",
        )
        self.config = FiscalSettings.objects.create(
            environment="sandbox",
            enabled=False,
            service_code="02800",
        )
        self.previous = TaxRate.objects.create(
            configuration=self.config,
            month=date(2026, 9, 1),
            iss="2.90",
            checked_at=timezone.now(),
            checked_by=self.user,
        )

    def test_superuser_whatsapp_is_normalized_and_invalid_number_is_rejected(self):
        self.user.refresh_from_db()
        self.assertEqual(self.user.administrative_whatsapp, "5511999999999")
        self.user.administrative_whatsapp = "123"
        with self.assertRaisesMessage(ValidationError, "WhatsApp válido"):
            self.user.save()

    @patch("apps.billing.fiscal.fiscal_today", return_value=date(2026, 10, 1))
    @patch("apps.integrations.whatsapp.client.EvolutionClient.send_text")
    def test_sends_both_links_once_per_month(self, send_text, _today):
        self.assertEqual(send_tax_rate_whatsapp_reminders(), 1)
        number, text = send_text.call_args.args
        self.assertEqual(number, "5511999999999")
        self.assertIn(
            "https://app.contabilizei.com.br/painel-de-controle/#/minhas-aliquotas",
            text,
        )
        self.assertIn("https://homolog.vemdedelivery.example/superadmin/billing/taxrate/add/", text)
        self.assertIn("month=2026-10-01", text)
        self.assertIn("iss=2.90", text)
        self.assertIn("Última alíquota confirmada: 2.90% (09/2026)", text)

        self.assertEqual(send_tax_rate_whatsapp_reminders(), 0)
        self.assertEqual(send_text.call_count, 1)
        reminder = TaxRateWhatsAppReminder.objects.get()
        self.assertEqual(reminder.status, "SENT")
        self.assertEqual(reminder.attempts, 1)
        self.assertIsNotNone(reminder.sent_at)

    @patch("apps.billing.fiscal.fiscal_today", return_value=date(2026, 10, 1))
    @patch("apps.integrations.whatsapp.client.EvolutionClient.send_text")
    def test_confirmed_month_sends_nothing(self, send_text, _today):
        TaxRate.objects.create(
            configuration=self.config,
            month=date(2026, 10, 1),
            iss="2.90",
            checked_at=timezone.now(),
            checked_by=self.user,
        )
        self.assertEqual(send_tax_rate_whatsapp_reminders(), 0)
        send_text.assert_not_called()
        self.assertFalse(TaxRateWhatsAppReminder.objects.exists())

    @patch("apps.billing.fiscal.fiscal_today", return_value=date(2026, 10, 1))
    @patch("apps.integrations.whatsapp.client.EvolutionClient.send_text")
    def test_failed_delivery_is_retried_until_provider_confirms(self, send_text, _today):
        send_text.side_effect = [EvolutionError("unavailable"), None]
        self.assertEqual(send_tax_rate_whatsapp_reminders(), 0)
        reminder = TaxRateWhatsAppReminder.objects.get()
        self.assertEqual(reminder.status, "FAILED")
        self.assertEqual(reminder.attempts, 1)

        self.assertEqual(send_tax_rate_whatsapp_reminders(), 1)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, "SENT")
        self.assertEqual(reminder.attempts, 2)
        self.assertEqual(send_text.call_count, 2)

    @patch("apps.billing.fiscal.fiscal_today", return_value=date(2026, 10, 1))
    @patch("apps.integrations.whatsapp.client.EvolutionClient.send_text")
    def test_user_without_admin_whatsapp_is_skipped(self, send_text, _today):
        self.User.objects.filter(pk=self.user.pk).update(administrative_whatsapp="")
        self.assertEqual(send_tax_rate_whatsapp_reminders(), 0)
        send_text.assert_not_called()
        self.assertFalse(TaxRateWhatsAppReminder.objects.exists())


    @patch("apps.integrations.whatsapp.client.EvolutionClient.send_text")
    def test_manual_test_command_sends_without_consuming_monthly_reminder(self, send_text):
        call_command("send_tax_rate_whatsapp_test", username=self.user.username, verbosity=0)
        number, text = send_text.call_args.args
        self.assertEqual(number, "5511999999999")
        self.assertIn("🧪 TESTE", text)
        self.assertIn(
            "https://app.contabilizei.com.br/painel-de-controle/#/minhas-aliquotas",
            text,
        )
        self.assertRegex(
            text,
            r"https://homolog\.vemdedelivery\.example/superadmin/billing/taxrate/\d+/change/",
        )
        self.assertFalse(TaxRateWhatsAppReminder.objects.exists())

    def test_daily_schedule_exists_at_0805(self):
        from django.conf import settings

        row = settings.CELERY_BEAT_SCHEDULE["billing-tax-rate-whatsapp-reminder"]
        self.assertEqual(row["task"], "apps.billing.tasks.send_tax_rate_whatsapp_reminders")
        self.assertEqual(row["schedule"]._orig_hour, 8)
        self.assertEqual(row["schedule"]._orig_minute, 5)
