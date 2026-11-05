"""Single-order read-only inspection; safe even for an uncertain remote operation."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_delivery_audit import audit_delivery


class Command(BaseCommand):
    help = 'Audita uma entrega sandbox 99Food sem consultar provedor ou reenviar comandos.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', required=True)
        parser.add_argument('--order-id', required=True, help='ID externo do pedido 99Food')

    def handle(self, *args, **options):
        try:
            report = audit_delivery(tenant_slug=options['tenant'], order_id=options['order_id'])
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write('Pedido local #%s; externo=%s; status=%s; modalidade=%s' % (
            report['order_id'], report['external_id'], report['local_status'], report['delivery_by']))
        self.stdout.write('Diagnóstico: %s; orderFinish processado=%s' % (
            report['assessment'], report['finish_webhook_processed']))
        for cmd in report['commands']:
            self.stdout.write('Outbox #%s: %s, estado=%s, tentativas=%s' % (
                cmd['id'], cmd['target'], cmd['state'], cmd['attempts']))
        for event in report['events']:
            self.stdout.write('Inbox #%s: %s, estado=%s' % (
                event['id'], event['code'], event['state']))
        self.stdout.write(report['instruction'])
