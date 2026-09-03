import base64
import json
import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.test import (
    Client,
    TestCase,
    TransactionTestCase,
    override_settings,
    skipUnlessDBFeature,
)
from django.urls import reverse
from django.utils import timezone

from apps.integrations.models import (
    WhatsAppAlert,
    WhatsAppIntegrationEvent,
    WhatsAppIntegrationState,
)
from apps.integrations.tasks import monitor_whatsapp, send_whatsapp_alerts
from apps.integrations.whatsapp.client import EvolutionClient, EvolutionError
from apps.integrations.whatsapp.monitor import (
    check_connection,
    current_state,
    claim,
    release,
    receive_hint,
    request_action,
)
from apps.tenants.admin_site import tenant_admin_site

CONFIG = dict(
    EVOLUTION_MONITOR_ENABLED=True,
    EVOLUTION_AUTO_RECONNECT=True,
    EVOLUTION_API_URL="http://evolution:8080",
    EVOLUTION_API_KEY="test-key",
    EVOLUTION_INSTANCE="platform",
    EVOLUTION_MONITOR_ENVIRONMENT="homolog",
    EVOLUTION_WEBHOOK_TOKEN="x" * 40,
    EVOLUTION_ALERT_EMAILS=["admin@example.com"],
)


@override_settings(**CONFIG)
class MonitorTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client_mock = patch(
            "apps.integrations.whatsapp.monitor.EvolutionClient"
        ).start()
        self.addCleanup(patch.stopall)
        self.api = self.client_mock.return_value
        self.api.status.return_value = "close"
        self.row = current_state()

    def due(self):
        WhatsAppIntegrationState.objects.filter(pk=self.row.pk).update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )

    def test_three_attempts_are_durable_and_stop(self):
        check_connection()
        self.api.restart.assert_not_called()
        for _ in range(3):
            self.due()
            check_connection()
        self.assertEqual(self.api.restart.call_count, 3)
        for _ in range(3):
            self.due()
            check_connection()
        self.assertEqual(self.api.restart.call_count, 3)
        self.row.refresh_from_db()
        self.assertTrue(self.row.manual_required)
        self.assertEqual(self.row.attempts, 3)
        self.assertEqual(WhatsAppAlert.objects.count(), 1)

    def test_backoff_not_bypassed_by_frequent_polling(self):
        check_connection()
        self.due()
        before = timezone.now()
        check_connection()
        self.row.refresh_from_db()
        self.assertGreaterEqual(
            self.row.next_attempt_at, before + timedelta(seconds=180)
        )
        check_connection()
        self.api.restart.assert_called_once()

    def test_disabled_no_database_or_network(self):
        with override_settings(EVOLUTION_MONITOR_ENABLED=False):
            self.assertFalse(check_connection())
        self.api.status.assert_not_called()

    def test_auto_reconnect_disabled_still_monitors(self):
        with override_settings(EVOLUTION_AUTO_RECONNECT=False):
            check_connection()
            self.due()
            check_connection()
        self.api.restart.assert_not_called()

    def test_api_errors_never_restart(self):
        for reason in (
            "credentials",
            "not_found",
            "unavailable",
            "invalid_response",
            "rate_limit",
        ):
            self.api.status.side_effect = EvolutionError(reason)
            self.due()
            check_connection()
        self.api.restart.assert_not_called()
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, "error")

    def test_pairing_hint_requires_confirmed_not_open(self):
        receive_hint(pairing=True)
        self.api.status.return_value = "open"
        check_connection()
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, "open")
        self.assertIsNone(self.row.pairing_hint_at)
        receive_hint(pairing=True)
        self.api.status.return_value = "close"
        check_connection()
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, "pairing")
        self.assertTrue(self.row.manual_required)
        self.api.restart.assert_not_called()

    def test_connecting_does_not_fight_provider_reconnect(self):
        self.api.status.return_value = "connecting"
        check_connection()
        self.due()
        check_connection()
        self.api.restart.assert_not_called()
        WhatsAppIntegrationState.objects.filter(pk=self.row.pk).update(
            down_since=timezone.now() - timedelta(minutes=16)
        )
        check_connection()
        self.row.refresh_from_db()
        self.assertTrue(self.row.manual_required)

    def test_timeout_during_restart_still_consumes_attempt(self):
        check_connection()
        self.due()
        self.api.restart.side_effect = EvolutionError("unavailable")
        check_connection()
        self.row.refresh_from_db()
        self.assertEqual(self.row.attempts, 1)
        self.assertEqual(self.row.status, "error")
        self.assertIsNone(self.row.lease_token)

    def test_live_lease_prevents_work_and_expired_lease_recovers(self):
        pk, token = claim()
        self.assertFalse(check_connection())
        self.api.status.assert_not_called()
        WhatsAppIntegrationState.objects.filter(pk=pk).update(
            lease_until=timezone.now() - timedelta(seconds=1)
        )
        self.assertTrue(check_connection())
        release(pk, token)

    def test_recovery_stable_two_minutes_resets_incident_only_once(self):
        check_connection()
        WhatsAppIntegrationState.objects.filter(pk=self.row.pk).update(
            down_since=timezone.now() - timedelta(minutes=6)
        )
        check_connection()
        send_whatsapp_alerts()
        send_whatsapp_alerts()
        self.assertEqual(len(mail.outbox), 1)
        self.api.status.return_value = "open"
        check_connection()
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.incident)
        WhatsAppIntegrationState.objects.filter(pk=self.row.pk).update(
            online_since=timezone.now() - timedelta(minutes=3)
        )
        check_connection()
        self.row.refresh_from_db()
        self.assertIsNone(self.row.incident)
        send_whatsapp_alerts()
        send_whatsapp_alerts()
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(WhatsAppAlert.objects.filter(recovery=True).count(), 1)

    def test_smtp_uncertain_no_blind_resend(self):
        alert = WhatsAppAlert.objects.create(state=self.row)
        with patch(
            "apps.integrations.tasks.EmailMessage.send",
            side_effect=TimeoutError("secret"),
        ) as send:
            send_whatsapp_alerts()
            send_whatsapp_alerts()
            send.assert_called_once()
        alert.refresh_from_db()
        self.assertEqual(alert.status, "uncertain")

    def test_gap_in_monitoring_cannot_count_as_stable_recovery(self):
        check_connection()
        WhatsAppIntegrationState.objects.filter(pk=self.row.pk).update(
            checked_at=timezone.now() - timedelta(minutes=10),
            online_since=timezone.now() - timedelta(minutes=10),
        )
        self.api.status.return_value = "open"
        check_connection()
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.incident)
        self.assertGreater(self.row.online_since, timezone.now() - timedelta(seconds=5))

    def test_small_flaps_keep_same_incident_and_attempt_budget(self):
        check_connection()
        self.due()
        check_connection()
        self.row.refresh_from_db()
        incident = self.row.incident
        self.api.status.return_value = "open"
        check_connection()
        self.api.status.return_value = "close"
        check_connection()
        self.row.refresh_from_db()
        self.assertEqual(self.row.incident, incident)
        self.assertEqual(self.row.attempts, 1)

    def test_no_email_recipients_keeps_pending(self):
        alert = WhatsAppAlert.objects.create(state=self.row)
        with override_settings(EVOLUTION_ALERT_EMAILS=[]):
            send_whatsapp_alerts()
        alert.refresh_from_db()
        self.assertEqual(alert.status, "pending")

    def test_other_environment_never_sends_or_reconnects(self):
        WhatsAppAlert.objects.create(state=self.row)
        with override_settings(EVOLUTION_MONITOR_ENVIRONMENT="prod"):
            other = current_state()
            self.assertNotEqual(other.pk, self.row.pk)
            send_whatsapp_alerts()
        self.assertEqual(len(mail.outbox), 0)

    def test_manual_request_keeps_budget_and_cooldown(self):
        user = get_user_model().objects.create_superuser(
            username="root", email="root@example.com", password="safe-test"
        )
        request_action("restart", user)
        with self.assertRaises(EvolutionError):
            request_action("restart", user)
        check_connection()
        self.api.restart.assert_called_once()
        WhatsAppIntegrationState.objects.filter(pk=self.row.pk).update(
            action_at=None, attempts=3
        )
        with self.assertRaises(EvolutionError):
            request_action("restart", user)

    def test_check_command_stale_and_fresh(self):
        with self.assertRaises(CommandError):
            call_command("check_whatsapp_monitor", require_fresh=True)
        self.api.status.return_value = "open"
        check_connection()
        call_command("check_whatsapp_monitor", require_fresh=True)


@override_settings(**CONFIG)
class WebhookTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("evolution_webhook")
        self.data = {
            "instance": "platform",
            "event": "CONNECTION_UPDATE",
            "data": {"state": "close", "statusReason": 401},
        }

    def post(self, data=None, **kwargs):
        return self.client.post(
            self.url,
            json.dumps(data or self.data),
            content_type="application/json",
            HTTP_X_EVOLUTION_WEBHOOK_TOKEN="x" * 40,
            **kwargs
        )

    def test_requires_secret_and_instance_and_enabled(self):
        self.assertEqual(self.client.post(self.url, {}).status_code, 403)
        self.assertEqual(
            self.post({**self.data, "instance": "tenant"}).status_code, 400
        )
        with override_settings(EVOLUTION_MONITOR_ENABLED=False):
            self.assertEqual(self.post().status_code, 403)
        self.assertFalse(WhatsAppIntegrationState.objects.exists())

    @patch("apps.integrations.tasks.monitor_whatsapp.delay")
    def test_hint_only_and_dedup(self, delay):
        self.assertEqual(self.post().status_code, 202)
        self.assertEqual(self.post().status_code, 202)
        delay.assert_called_once()
        row = current_state()
        self.assertEqual(row.status, "unknown")
        self.assertIsNotNone(row.pairing_hint_at)
        self.assertFalse(WhatsAppIntegrationEvent.objects.exists())

    @patch(
        "apps.integrations.tasks.monitor_whatsapp.delay",
        side_effect=RuntimeError("broker"),
    )
    def test_broker_failure_still_durable(self, delay):
        self.assertEqual(self.post().status_code, 202)
        self.assertTrue(current_state().webhook_pending)

    def test_unrelated_and_oversized_events_rejected(self):
        self.assertEqual(
            self.post({**self.data, "event": "MESSAGES_UPSERT"}).status_code, 204
        )
        self.assertEqual(
            self.post({**self.data, "padding": "a" * 262145}).status_code, 413
        )
        self.assertFalse(WhatsAppIntegrationState.objects.exists())

    @patch("apps.integrations.tasks.monitor_whatsapp.delay")
    def test_delayed_webhook_cannot_overwrite_confirmed_state(self, delay):
        row = current_state()
        row.status = "open"
        row.checked_at = timezone.now()
        row.save()
        self.post()
        row.refresh_from_db()
        self.assertEqual(row.status, "open")
        self.assertEqual(row.attempts, 0)

    @patch("apps.integrations.tasks.monitor_whatsapp.delay")
    def test_qr_payload_is_discarded(self, delay):
        secret = "PRIVATE-PAIRING-MATERIAL"
        self.post(
            {
                "event": "QRCODE_UPDATED",
                "instance": "platform",
                "data": {"qrcode": {"base64": secret}},
            }
        )
        self.assertNotIn(secret, str(list(WhatsAppIntegrationState.objects.values())))
        self.assertNotIn(secret, str(list(WhatsAppIntegrationEvent.objects.values())))


@override_settings(**CONFIG)
class AdminTests(TestCase):
    def setUp(self):
        self.root = get_user_model().objects.create_superuser(
            username="root", email="root@example.com", password="safe-test"
        )
        from apps.tenants.models import Tenant

        tenant = Tenant.objects.create(
            name="Teste", slug="test-evolution", whatsapp_number="5511988881111"
        )
        self.staff = get_user_model().objects.create_user(
            username="staff",
            password="safe-test",
            is_staff=True,
            is_tenant_admin=True,
            tenant=tenant,
        )
        self.url = reverse("super_admin:evolution_panel")
        self.row = current_state()

    def test_only_active_superadmin_can_read_or_act(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        for user in (
            self.staff,
            get_user_model().objects.create_user(
                username="ordinary", password="safe-test"
            ),
        ):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 302)
            self.assertEqual(
                self.client.post(self.url, {"action": "restart"}).status_code, 302
            )
        self.client.force_login(self.root)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.root.is_active = False
        self.root.save()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_not_registered_in_tenant_admin(self):
        for model in (
            WhatsAppIntegrationState,
            WhatsAppIntegrationEvent,
            WhatsAppAlert,
        ):
            self.assertNotIn(model, tenant_admin_site._registry)

    def test_staff_with_model_permissions_still_denied(self):
        from django.contrib.auth.models import Permission

        self.staff.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="integrations")
        )
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(
            self.client.post(self.url, {"action": "pair"}).status_code, 302
        )
        with self.assertRaises(EvolutionError):
            request_action("restart", self.staff)

    @patch("apps.integrations.admin.EvolutionClient")
    def test_qr_never_calls_connect_if_already_open(self, api):
        self.row.status = "pairing"
        self.row.manual_required = True
        self.row.save()
        api.return_value.status.return_value = "open"
        self.client.force_login(self.root)
        self.assertEqual(
            self.client.post(self.url, {"action": "pair"}).status_code, 302
        )
        api.return_value.connect.assert_not_called()

    def test_panel_off_has_no_provider_call(self):
        self.client.force_login(self.root)
        with override_settings(EVOLUTION_MONITOR_ENABLED=False), patch(
            "apps.integrations.admin.EvolutionClient"
        ) as api:
            response = self.client.get(self.url)
            self.assertContains(response, "Monitoramento desabilitado")
            self.client.post(self.url, {"action": "pair"})
            api.assert_not_called()

    def test_csrf_required_and_no_mutating_get(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.root)
        response = client.post(self.url, {"action": "restart"})
        self.assertEqual(response.status_code, 403)
        client.get(self.url + "?action=restart")
        self.row.refresh_from_db()
        self.assertFalse(self.row.manual_requested)

    @patch("apps.integrations.admin.EvolutionClient")
    def test_qr_private_and_not_persisted(self, api):
        self.row.status = "pairing"
        self.row.manual_required = True
        self.row.save()
        api.return_value.status.return_value = "close"
        qr = (
            "data:image/png;base64,"
            + base64.b64encode(b"\x89PNG\r\n\x1a\n-test-image").decode()
        )
        api.return_value.connect.return_value = {"base64": qr}
        self.client.force_login(self.root)
        response = self.client.post(self.url, {"action": "pair"})
        self.assertContains(response, qr)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotIn(qr, str(list(WhatsAppIntegrationEvent.objects.values())))
        self.assertNotContains(self.client.get(self.url), qr)

    def test_admin_cannot_edit_or_delete_history(self):
        event = WhatsAppIntegrationEvent.objects.create(
            state=self.row, kind="test", description="Teste"
        )
        self.client.force_login(self.root)
        url = reverse(
            "super_admin:integrations_whatsappintegrationevent_change", args=[event.pk]
        )
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(
            self.client.post(url, {"description": "changed"}).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                reverse(
                    "super_admin:integrations_whatsappintegrationevent_delete",
                    args=[event.pk],
                )
            ).status_code,
            403,
        )


@override_settings(**CONFIG)
class ClientTests(TestCase):
    def session(self, body, code=200):
        response = Mock(status_code=code)
        response.iter_content.return_value = [json.dumps(body).encode()]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.request.return_value = response
        return session

    def test_http_fixed_url_no_redirect_proxy_and_timeout(self):
        session = self.session(
            {"instance": {"instanceName": "platform", "state": "open"}}
        )
        with patch(
            "apps.integrations.whatsapp.client.requests.Session", return_value=session
        ):
            self.assertEqual(EvolutionClient().status(), "open")
        self.assertFalse(session.trust_env)
        args = session.request.call_args
        self.assertEqual(
            args.args,
            ("GET", "http://evolution:8080/instance/connectionState/platform"),
        )
        self.assertFalse(args.kwargs["allow_redirects"])
        self.assertEqual(args.kwargs["headers"]["apikey"], "test-key")

    def test_forbidden_and_oversize_and_wrong_instance(self):
        for body, status in (
            ({}, 302),
            ({}, 401),
            ({"secret": "a" * 600000}, 200),
            ({"instance": {"instanceName": "other", "state": "open"}}, 200),
        ):
            with patch(
                "apps.integrations.whatsapp.client.requests.Session",
                return_value=self.session(body, status),
            ):
                with self.assertRaises(EvolutionError) as exc:
                    EvolutionClient().status()
                self.assertNotIn("secret", str(exc.exception))

    def test_reject_invalid_base_and_destructive_operation(self):
        with override_settings(EVOLUTION_API_URL="https://user:secret@host/"):
            with self.assertRaises(EvolutionError):
                EvolutionClient().status()
        with self.assertRaises(EvolutionError):
            EvolutionClient().request("DELETE", "instance/logout")


@override_settings(**CONFIG)
@skipUnlessDBFeature("has_select_for_update")
class MonitorConcurrencyTests(TransactionTestCase):
    def test_two_workers_restart_only_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        row = current_state()
        WhatsAppIntegrationState.objects.filter(pk=row.pk).update(
            status="close",
            incident=uuid.uuid4(),
            down_since=timezone.now() - timedelta(minutes=1),
            next_attempt_at=timezone.now() - timedelta(seconds=1),
        )
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                check_connection()
            finally:
                connection.close()

        with patch("apps.integrations.whatsapp.monitor.EvolutionClient") as client:
            client.return_value.status.return_value = "close"
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = [executor.submit(worker) for _ in range(2)]
                for result in results:
                    result.result(timeout=20)
            client.return_value.restart.assert_called_once()
        row.refresh_from_db()
        self.assertEqual(row.attempts, 1)

    def test_two_workers_send_one_alert(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        row = current_state()
        WhatsAppAlert.objects.create(state=row)
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                send_whatsapp_alerts()
            finally:
                connection.close()

        with patch("apps.integrations.tasks.EmailMessage.send", return_value=1) as send:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = [executor.submit(worker) for _ in range(2)]
                for result in results:
                    result.result(timeout=20)
            send.assert_called_once()
