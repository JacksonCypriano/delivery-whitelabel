"""Durable inbox/outbox. No secrets are exposed through merchant resources."""
from django.db import models
from django.core.exceptions import ValidationError

PROVIDERS = [('ifood', 'iFood'), ('99food', '99Food')]

class Connection(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.PROTECT)
    provider = models.CharField(max_length=10, choices=PROVIDERS)
    merchant_id = models.CharField(max_length=128)
    merchant_name = models.CharField(max_length=180, blank=True)
    mode = models.CharField(max_length=12, choices=[('simulation','Simulação local'),('test','Aplicativo de teste'),('live','Conta real')], default='test')
    enabled = models.BooleanField(default=False)
    status = models.CharField(max_length=24, default='awaiting_authorization')
    last_sync = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['provider','mode','merchant_id'], name='channel_merchant_owner_unique')]

class AppToken(models.Model):
    key = models.CharField(max_length=40, unique=True)
    encrypted_token = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True)
    poll_after = models.DateTimeField(null=True)

class ExternalOrder(models.Model):
    connection = models.ForeignKey(Connection, on_delete=models.PROTECT, related_name='orders')
    order = models.OneToOneField('orders.Order', on_delete=models.PROTECT, related_name='external_order')
    external_id = models.CharField(max_length=128)
    display_id = models.CharField(max_length=80, blank=True)
    delivery_by = models.CharField(max_length=24, default='UNKNOWN')
    paid = models.BooleanField(default=False)
    prepare_after = models.DateTimeField(null=True, blank=True)
    scheduled_until = models.DateTimeField(null=True, blank=True)
    platform_notes = models.TextField(blank=True)
    payment_summary = models.CharField(max_length=200, blank=True)
    encrypted_snapshot = models.TextField()
    financials = models.JSONField(default=dict)  # Amounts only; never buyer identifiers.
    last_event_at = models.DateTimeField(null=True)
    stock_state = models.CharField(max_length=24, default='pending')
    warning = models.CharField(max_length=240, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['connection','external_id'], name='channel_external_order_unique')]

class ProductLink(models.Model):
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE)
    external_code = models.CharField(max_length=128)
    product = models.ForeignKey('stores.Product', on_delete=models.PROTECT)
    def save(self,*args,**kwargs):
        if self.product.tenant_id != self.connection.tenant_id:
            raise ValidationError('Produto e conexão devem pertencer à mesma loja.')
        return super().save(*args,**kwargs)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['connection','external_code'], name='channel_product_link_unique')]

class Inbox(models.Model):
    connection = models.ForeignKey(Connection, on_delete=models.PROTECT, related_name='events')
    external_id = models.CharField(max_length=128)
    order_id = models.CharField(max_length=128)
    code = models.CharField(max_length=80)
    occurred_at = models.DateTimeField()
    payload = models.JSONField(default=dict)  # Event identifiers only; order PII stays encrypted.
    state = models.CharField(max_length=20, default='pending', db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt = models.DateTimeField(null=True)
    error = models.CharField(max_length=240, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['connection','external_id'], name='channel_event_unique')]
        indexes = [models.Index(fields=['state','next_attempt'])]

class Outbox(models.Model):
    external_order = models.ForeignKey(ExternalOrder, on_delete=models.PROTECT, related_name='commands')
    target = models.CharField(max_length=24)
    from_status = models.CharField(max_length=24)
    payload = models.JSONField(default=dict)
    state = models.CharField(max_length=20, default='pending', db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt = models.DateTimeField(null=True)
    error = models.CharField(max_length=240, blank=True)
    actor = models.ForeignKey('accounts.User', null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['external_order','target'], name='channel_command_unique')]
