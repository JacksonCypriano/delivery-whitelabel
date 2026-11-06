"""Explicit opt-in sandbox authentication check; never prints credentials."""
from django.core.management.base import BaseCommand, CommandError
from apps.channels.connectors import ProviderError
from apps.channels.food99_auth import get_shop_token


class Command(BaseCommand):
    help = "Confere autenticação da loja 99Food sandbox, sem exibir tokens."

    def add_arguments(self, parser):
        parser.add_argument("--app-shop-id", required=True)
        parser.add_argument("--refresh", action="store_true", help="Solicita um token novo")
        parser.add_argument("--execute", action="store_true", help="Autoriza comunicação com API externa")

    def handle(self, *args, **options):
        if not options["execute"]:
            self.stdout.write("Modo seguro: nenhuma requisição efetuada. Use --execute para testar.")
            return
        try:
            get_shop_token(options["app_shop_id"], force_refresh=options["refresh"])
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS("Autenticação 99Food sandbox validada; token salvo criptografado."))
