"""Explicit, opt-in one-shot remote confirm during controlled 99Food pilot."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_remote_confirm import confirm_existing


class Command(BaseCommand):
    help = 'Prévia/confirmação ÚNICA de pedido 99Food TESTE (somente piloto explicitamente habilitado).'

    def add_arguments(self, parser):
        parser.add_argument('--order-id', type=int, required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--confirm-remote', action='store_true')

    def handle(self, *args, **options):
        try:
            result = confirm_existing(order_id=options['order_id'],
                                      apply=options['apply'],
                                      confirm_remote=options['confirm_remote'])
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(' '.join(f'{k}={v}' for k, v in result.items()))
        if result['result'] == 'UNCERTAIN':
            self.stderr.write('NÃO repetir: verifique o estado oficial na 99Food.')
