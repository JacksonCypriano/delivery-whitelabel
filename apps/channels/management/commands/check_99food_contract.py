"""Print static 99Food contract gates; no provider access, no data mutation."""
from django.core.management.base import BaseCommand
from apps.channels.food99_operational_dryrun import CONTRACT_GATES


class Command(BaseCommand):
    help = 'Verifica pré-requisitos da 99Food sem acessar API ou modificar banco.'

    def handle(self, *args, **options):
        self.stdout.write('99Food — requisitos necessários para ativação operacional:')
        for key, label in CONTRACT_GATES:
            self.stdout.write(f'[PENDENTE] {key}: {label}')
        self.stdout.write('Operação mantida desabilitada. Nenhum pedido foi alterado.')
