from .base import CriticalTestCase
from apps.accounts.models import SecurityEvent
from apps.billing.models import BillingEvent, BillingAudit

class PanelPaginationTests(CriticalTestCase):
    def test_admin_event_pages_are_bounded_and_do_not_overlap(self):
        for i in range(26):
            SecurityEvent.objects.create(event="login_failed", scope="auth")
            BillingEvent.objects.create(event_id=f"paging-{i}", payment_id=f"pay-{i}", kind="PAYMENT_CREATED", environment="sandbox")
            BillingAudit.objects.create(tenant=self.tenant_a, action="pagination-test", detail=str(i))
        self.client.force_login(self.superuser)
        for resource in ["accounts-securityevent", "billing-billingevent", "billing-billingaudit"]:
            url = f"/api/superadmin/resources/{resource}/"
            first = self.client.get(url, HTTP_HOST="lvh.me")
            self.assertEqual(first.status_code, 200, first.content)
            self.assertEqual(len(first.json()["rows"]), 10)
            second = self.client.get(url, {"p": 2}, HTTP_HOST="lvh.me")
            self.assertEqual(second.status_code, 200, second.content)
            self.assertFalse({x["id"] for x in first.json()["rows"]} & {x["id"] for x in second.json()["rows"]})
            larger = self.client.get(url, {"page_size": 25}, HTTP_HOST="lvh.me")
            self.assertEqual(len(larger.json()["rows"]), 25)
            bounded = self.client.get(url, {"page_size": 99999, "all": 1}, HTTP_HOST="lvh.me")
            self.assertEqual(len(bounded.json()["rows"]), 10)
