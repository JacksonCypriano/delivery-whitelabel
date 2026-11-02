"""Manually verify a sandbox order without exposing PII or changing order state."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_orders import get_order_detail


class Command(BaseCommand):
    help = "Consulta pedido 99Food sandbox sem armazenar/exibir dados pessoais."

    def add_arguments(self, parser):
        parser.add_argument("--app-shop-id", required=True)
        parser.add_argument("--order-id", required=True)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        if not options["execute"]:
            self.stdout.write("Modo seguro: nenhuma chamada externa. Use --execute para consultar.")
            return
        try:
            get_order_detail(options["app_shop_id"], options["order_id"])
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS("Consulta ao pedido 99Food validada (sem gravar ou exibir dados do cliente)."))
