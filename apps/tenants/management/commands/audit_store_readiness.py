from django.core.management.base import BaseCommand

from apps.marketplace.models import MarketplaceProfile
from apps.tenants.onboarding import get_store_setup


class Command(BaseCommand):
    help = "Audita lojas publicadas e, com --fix, remove do marketplace as que estão incompletas."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true", help="Despublica automaticamente lojas incompletas.")

    def handle(self, *args, **options):
        profiles = MarketplaceProfile.objects.select_related("tenant").filter(is_listed=True)
        incomplete = 0

        for profile in profiles:
            setup = get_store_setup(profile.tenant)
            if setup["complete"]:
                self.stdout.write(self.style.SUCCESS(f"OK: {profile.tenant.name}"))
                continue

            incomplete += 1
            missing = ", ".join(
                step["title"] for step in setup["steps"]
                if step.get("required", True) and not step["complete"]
            )
            self.stdout.write(self.style.WARNING(f"PENDENTE: {profile.tenant.name} — {missing}"))

            if options["fix"]:
                MarketplaceProfile.objects.filter(pk=profile.pk).update(is_listed=False)
                self.stdout.write("  -> removida do marketplace")

        if not incomplete:
            self.stdout.write(self.style.SUCCESS("Todas as lojas publicadas estão completas."))
        elif not options["fix"]:
            self.stdout.write(self.style.WARNING(f"{incomplete} loja(s) incompleta(s). Rode novamente com --fix para despublicar."))
