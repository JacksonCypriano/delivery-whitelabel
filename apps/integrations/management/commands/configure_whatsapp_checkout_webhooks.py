from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from apps.billing.models import TenantPaymentAccount
from apps.billing.provider import Asaas, BillingError, valid_id
from apps.billing.online import ACCOUNT_STATUS_EVENTS

EVENTS = {
    "PAYMENT_CREATED",
    "PAYMENT_RECEIVED",
    "PAYMENT_CONFIRMED",
    "PAYMENT_DELETED",
    "PAYMENT_REFUNDED",
}


class Command(BaseCommand):
    help = "Confere/provisiona eventos Pix nas subcontas existentes. Sem --apply, somente consulta."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--tenant", type=int)

    def handle(self, *args, **options):
        url = str(getattr(settings, "ASAAS_WEBHOOK_URL", "") or "").strip()
        token = settings.ASAAS_WEBHOOK_TOKEN
        if not url or len(token) < 32:
            raise CommandError(
                "Configure ASAAS_WEBHOOK_URL e ASAAS_WEBHOOK_TOKEN antes de continuar."
            )
        rows = TenantPaymentAccount.objects.exclude(provider_account_id="").exclude(
            encrypted_api_key=""
        )
        if options["tenant"]:
            rows = rows.filter(tenant_id=options["tenant"])
        failed = False
        for account in rows:
            try:
                api = Asaas(api_key=account.get_api_key())
                offset = 0
                found = []
                while True:
                    page = api.request(
                        "GET", "/webhooks", params={"offset": offset, "limit": 100}
                    )
                    found.extend(w for w in page.get("data", []) if w.get("url") == url)
                    if not page.get("hasMore"):
                        break
                    offset += 100
                if not options["apply"]:
                    ready = any(
                        EVENTS.issubset(set(w.get("events", [])))
                        and w.get("enabled")
                        and not w.get("interrupted")
                        for w in found
                    )
                    self.stdout.write(
                        f"Loja {account.tenant_id}: {'eventos presentes' if ready else 'atualização necessária'}"
                    )
                    continue
                current = found[0] if found else {}
                body = {
                    "name": "VemDeDelivery - conta e pedidos Pix",
                    "url": url,
                    "email": account.email,
                    "enabled": True,
                    "interrupted": False,
                    "apiVersion": 3,
                    "authToken": token,
                    "sendType": "SEQUENTIALLY",
                    "events": sorted(
                        set(current.get("events", []))
                        | set(ACCOUNT_STATUS_EVENTS)
                        | EVENTS
                    ),
                }
                if current:
                    api.request(
                        "PUT", "/webhooks/" + valid_id(current.get("id")), json=body
                    )
                else:
                    api.request("POST", "/webhooks", json=body)
                self.stdout.write(f"Loja {account.tenant_id}: webhook configurado")
            except (BillingError, ValueError):
                failed = True
                self.stderr.write(
                    f"Loja {account.tenant_id}: falha; confira a configuração da subconta."
                )
        if failed:
            raise CommandError("Uma ou mais subcontas precisam de revisão.")
