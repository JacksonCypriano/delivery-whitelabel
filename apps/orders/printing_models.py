import uuid
from django.db import models


class PrintDevice(models.Model):
    tenant = models.OneToOneField('tenants.Tenant', on_delete=models.CASCADE)
    name = models.CharField(max_length=100, default='Balcão')
    token_hash = models.CharField(max_length=64, blank=True)
    active = models.BooleanField(default=False)
    paper_mm = models.PositiveSmallIntegerField(default=80)
    copies = models.PositiveSmallIntegerField(default=1)
    templates = models.JSONField(default=list)
    auto_enabled = models.BooleanField(default=False)
    trigger = models.CharField(max_length=30, default='confirmed')
    last_seen = models.DateTimeField(null=True, blank=True)


class PrintJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(PrintDevice, on_delete=models.CASCADE)
    order = models.ForeignKey('orders.Order', on_delete=models.PROTECT)
    template = models.CharField(max_length=20)
    event_key = models.CharField(max_length=100)
    text = models.TextField()
    paper_mm = models.PositiveSmallIntegerField()
    copies = models.PositiveSmallIntegerField(default=1)
    state = models.CharField(max_length=20, default='queued', db_index=True)
    reprint_of = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['device','order','template','event_key'],name='print_event_once')]
