from datetime import time

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class ProspectingBatch(models.Model):
    filename = models.CharField("arquivo", max_length=255)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    total_contacts = models.PositiveIntegerField("contatos na planilha", default=0)
    queued_contacts = models.PositiveIntegerField("novos adicionados", default=0)
    skipped_contacted = models.PositiveIntegerField("já contatados", default=0)
    skipped_duplicate = models.PositiveIntegerField("duplicados/na fila", default=0)
    invalid_contacts = models.PositiveIntegerField("inválidos", default=0)
    failed_contacts = models.PositiveIntegerField("falhas explícitas", default=0)
    is_active = models.BooleanField("ativa na fila", default=True, db_index=True)
    removed_at = models.DateTimeField("removida em", blank=True, null=True)
    contacts_index_complete = models.BooleanField(
        "índice completo da planilha",
        default=False,
        help_text="Indica que todos os telefones válidos únicos da planilha foram indexados.",
    )

    class Meta:
        verbose_name = "lote de prospecção"
        verbose_name_plural = "prospecção WhatsApp"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.filename} ({self.created_at:%d/%m/%Y %H:%M})"

    @property
    def contacted_contacts(self) -> int:
        if self.contacts_index_complete:
            return self.contacts.filter(
                phone__in=ProspectingSentPhone.objects.values("phone")
            ).count()
        return (
            self.items.filter(status=ProspectingQueueItem.Status.SENT).count()
            + self.skipped_contacted
        )

    @property
    def pending_contacts(self) -> int:
        return self.items.filter(
            status__in=(ProspectingQueueItem.Status.PENDING, ProspectingQueueItem.Status.PROCESSING)
        ).count()

    @property
    def unknown_contacts(self) -> int:
        return self.items.filter(status=ProspectingQueueItem.Status.UNKNOWN).count()


class ProspectingBatchContact(models.Model):
    """Índice permanente dos telefones válidos que pertenciam a uma planilha."""

    batch = models.ForeignKey(
        ProspectingBatch,
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name="planilha",
    )
    phone = models.CharField("telefone", max_length=20, db_index=True)
    establishment = models.CharField("nome da loja", max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "contato de planilha de prospecção"
        verbose_name_plural = "contatos de planilhas de prospecção"
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "phone"),
                name="prospect_batch_contact_unique",
            )
        ]
        indexes = [
            models.Index(fields=("batch", "phone"), name="prospect_batch_phone_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.establishment} · {self.phone}"


class ProspectingSentPhone(models.Model):
    """Trava permanente contra uma segunda abordagem automática."""

    phone = models.CharField("telefone", max_length=20, primary_key=True)
    contacted_at = models.DateTimeField("registrado em", auto_now_add=True)

    class Meta:
        verbose_name = "telefone já abordado"
        verbose_name_plural = "telefones já abordados"
        ordering = ("-contacted_at", "phone")

    def __str__(self) -> str:
        return self.phone


class ProspectingQueueItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        PROCESSING = "PROCESSING", "Processando"
        SENT = "SENT", "Enviado"
        REJECTED = "REJECTED", "Rejeitado"
        UNKNOWN = "UNKNOWN", "Entrega incerta"

    batch = models.ForeignKey(
        ProspectingBatch,
        on_delete=models.PROTECT,
        related_name="items",
        verbose_name="lote",
    )
    phone = models.CharField("telefone", max_length=20)
    establishment = models.CharField("nome da loja", max_length=255)
    status = models.CharField(
        "situação",
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "item da fila de prospecção"
        verbose_name_plural = "itens da fila de prospecção"
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "phone"),
                name="prospect_batch_queue_phone_unique",
            )
        ]
        indexes = [
            models.Index(fields=("status", "created_at"), name="prospect_status_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.establishment} · {self.phone}"


class ProspectingControl(models.Model):
    """Configuração singleton da janela e do ritmo da prospecção."""

    singleton_id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField("envios ativos", default=False)
    start_time = models.TimeField("horário inicial", default=time(9, 0))
    end_time = models.TimeField("horário final", default=time(21, 0))
    messages_per_minute = models.PositiveSmallIntegerField(
        "contatos por minuto",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    # 0=segunda ... 6=domingo.
    weekdays = models.CharField("dias permitidos", max_length=13, default="0,1,2,3,4")

    class Meta:
        verbose_name = "controle de prospecção"
        verbose_name_plural = "controle de prospecção"

    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(singleton_id=1)
        return obj

    @property
    def weekday_numbers(self) -> set[int]:
        values = set()
        for value in (self.weekdays or "").split(","):
            value = value.strip()
            if value.isdigit() and 0 <= int(value) <= 6:
                values.add(int(value))
        return values

    def is_allowed_at(self, moment=None) -> bool:
        if not self.enabled:
            return False

        local_now = timezone.localtime(moment or timezone.now())
        if local_now.weekday() not in self.weekday_numbers:
            return False

        current_time = local_now.time().replace(tzinfo=None)
        start = self.start_time
        end = self.end_time

        if start == end:
            return False
        if start < end:
            return start <= current_time < end
        return current_time >= start or current_time < end
