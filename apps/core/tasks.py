"""Scheduled housekeeping for temporary admin resources."""

from celery import shared_task
from .selection_cleanup import prune_expired_selections


@shared_task
def prune_expired_admin_selections():
    return prune_expired_selections()
