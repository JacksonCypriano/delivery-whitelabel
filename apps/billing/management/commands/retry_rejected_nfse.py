import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.billing.fiscal import process_fiscal
from apps.billing.models import BillingCustomer, FiscalInvoice, Invoice
from apps.billing.provider import Asaas, BillingError, environment
from apps.billing.services import sync_billing_customer_remote


class Command(BaseCommand):
    help = "Libera e repete uma NFS-e rejeitada explicitamente, após confirmar que o Asaas não criou nota para a cobrança."

    def add_arguments(self, parser):
        parser.add_argument("--invoice", required=True, help="UUID da cobrança VemDeDelivery")

    def handle(self, *args, **options):
        try:
            invoice_id = uuid.UUID(options["invoice"])
        except (TypeError, ValueError):
            raise CommandError("Informe um UUID de cobrança válido.")

        bill = Invoice.objects.filter(pk=invoice_id, environment=environment()).first()
        if not bill:
            raise CommandError("Cobrança não encontrada neste ambiente.")
        if bill.status != "PAID" or not bill.provider_id:
            raise CommandError("A cobrança precisa estar paga e conciliada no Asaas.")

        note = FiscalInvoice.objects.filter(invoice=bill).first()
        if not note:
            raise CommandError("Ainda não existe registro fiscal para esta cobrança.")
        if note.provider_id:
            raise CommandError("A nota já possui ID no Asaas; não é seguro criar outra.")

        api = Asaas()
        found = api.request("GET", "/invoices", params={"payment": bill.provider_id, "limit": 100})
        rows = found.get("data")
        if not isinstance(rows, list) or found.get("hasMore") or rows:
            raise CommandError("O Asaas retornou nota existente ou consulta inconclusiva. Revise manualmente; nenhuma nova nota foi criada.")

        customer = BillingCustomer.objects.filter(
            tenant_id=bill.tenant_id, environment=bill.environment
        ).first()
        if not customer or customer.provider_id != bill.customer_id_external:
            raise CommandError("Pagador local ausente ou divergente da cobrança.")
        try:
            sync_billing_customer_remote(api, customer)
        except BillingError as exc:
            raise CommandError(str(exc))

        with transaction.atomic():
            note = FiscalInvoice.objects.select_for_update().get(pk=note.pk)
            if note.provider_id:
                raise CommandError("A nota ganhou ID no Asaas durante a operação; interrompido por segurança.")
            note.attempted = False
            note.status = "PENDING"
            note.notice = "Nova tentativa fiscal liberada após rejeição explícita e confirmação de ausência de NFS-e no Asaas."
            note.save(update_fields=["attempted", "status", "notice"])

        process_fiscal(bill.pk)
        note.refresh_from_db()
        self.stdout.write(f"Situação fiscal após tentativa: {note.status}")
        self.stdout.write(f"Aviso: {note.notice or '-'}")
        if note.provider_id:
            self.stdout.write(self.style.SUCCESS(f"NFS-e registrada no Asaas: {note.provider_id}"))
        elif note.status == "ERROR":
            raise CommandError("O Asaas rejeitou novamente a emissão. Confira o aviso acima.")
        else:
            self.stdout.write(self.style.WARNING("Emissão ainda sem ID; aguarde/concilie antes de nova tentativa."))
