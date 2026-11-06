from django.core.management.base import BaseCommand
from apps.core.selection_cleanup import prune_expired_selections


class Command(BaseCommand):
    help = "Remove seleções administrativas expiradas e seus itens temporários."

    def handle(self, *args, **options):
        total = prune_expired_selections()
        self.stdout.write(f"{total} seleções expiradas removidas.")
