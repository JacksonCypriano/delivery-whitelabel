"""Platform inbound sales, isolated from tenant conversations and outbound batches."""
from django.conf import settings
from django.db import models


class CommercialControl(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    instance = models.CharField(max_length=100, blank=True)
    enabled = models.BooleanField(default=False)
    catalog_fingerprint = models.CharField(max_length=64, blank=True)
    catalog_reviewed_at = models.DateTimeField(null=True, blank=True)
    demo_url = models.URLField(blank=True)
    contact_url = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]


class CommercialArticle(models.Model):
    """Immutable revisions: only the most recent revision of a slug is considered."""
    slug = models.SlugField(max_length=80)
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=160)
    body = models.TextField()
    published = models.BooleanField(default=False)
    source_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['slug', 'version'], name='commercial_article_revision')]


class CommercialConversation(models.Model):
    instance = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    name = models.CharField(max_length=120, blank=True)
    stage = models.CharField(max_length=20, default='new', choices=[(x,x) for x in ('new','attending','qualified','demo','negotiation','converted','lost')])
    source = models.CharField(max_length=30, default='whatsapp')
    marketing_lead = models.ForeignKey('marketplace.MarketingLead', null=True, blank=True, on_delete=models.SET_NULL)
    paused = models.BooleanField(default=False)
    opted_out = models.BooleanField(default=False)
    reason = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['instance','phone'], name='commercial_instance_contact')]


class CommercialMessage(models.Model):
    conversation = models.ForeignKey(CommercialConversation, related_name='messages', on_delete=models.CASCADE)
    provider_id = models.CharField(max_length=160)
    text = models.TextField(blank=True)
    from_me = models.BooleanField(default=False)
    state = models.CharField(max_length=20, default='queued', db_index=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reply = models.TextField(blank=True)
    reply_id = models.CharField(max_length=160, blank=True)
    catalog_fingerprint = models.CharField(max_length=64, blank=True)
    sources = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['conversation','provider_id'], name='commercial_message_once')]


class CommercialAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    conversation = models.ForeignKey(CommercialConversation, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)
