"""Explicit local-only projection of a reviewed, recent 99Food sandbox order."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_sandbox_promotion import promote_reviewed


class Command(BaseCommand):
    help = 'Prévia/promoção local de pedido 99Food revisado; NUNCA confirma na plataforma.'

    def add_arguments(self, parser):
        parser.add_argument('--staged-id', type=int, required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--confirm-brl', action='store_true')

    def handle(self, *args, **options):
        try:
            result = promote_reviewed(staged_id=options['staged_id'],
                        apply=options['apply'], confirm_brl=options['confirm_brl'])
        except ProviderError:
            raise CommandError('Promoção bloqueada: revisão, status, prazo ou configuração não elegível.') from None
        self.stdout.write(' '.join(f'{key}={value}' for key, value in result.items()))
        self.stdout.write('ATENÇÃO: pedido local sandbox; nenhum aceite foi enviado à 99Food.')
