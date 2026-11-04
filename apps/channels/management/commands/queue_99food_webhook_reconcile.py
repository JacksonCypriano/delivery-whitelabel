"""Opt-in HML shell command to dispatch safe quarantine reconciliation jobs."""
from django.core.management.base import BaseCommand, CommandError

from apps.channels.connectors import ProviderError
from apps.channels.food99_async_reconcile import queue_reconciliation


class Command(BaseCommand):
    help = "99Food HML: inspect or queue bounded, read-only quarantine reconciliation"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True)
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--apply", action="store_true",
                            help="Queue Celery tasks; never ACK or import operational orders")

    def handle(self, *args, **options):
        try:
            enqueue = None
            if options["apply"]:
                from apps.channels.tasks import reconcile_99food_quarantine_event
                enqueue = reconcile_99food_quarantine_event.delay
            result = queue_reconciliation(
                tenant_slug=options["tenant"], limit=options["limit"], enqueue=enqueue
            )
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
        except Exception:
            # Avoid printing a broker exception that could include credentials.
            raise CommandError("Não foi possível enviar as tarefas ao worker.") from None
        self.stdout.write(
            f"99Food {result['mode']}: selecionados={result['selected']} "
            f"enfileirados={result['queued']} ACK=False"
        )
