"""Bounded cleanup of expired global administrator selection snapshots."""

from django.utils import timezone
from apps.core.models import AdminSelection


def prune_expired_selections(batch_size=100):
    removed = 0
    while True:
        expired = list(
            AdminSelection.objects.filter(expires_at__lte=timezone.now())
            .order_by("expires_at")
            .values_list("pk", flat=True)[:batch_size]
        )
        if not expired:
            break
        # CASCADE removes snapshot items, never snapshots still valid.
        AdminSelection.objects.filter(pk__in=expired, expires_at__lte=timezone.now()).delete()
        removed += len(expired)
    return removed
