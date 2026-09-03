from django.apps import AppConfig


class BillingConfig(AppConfig):
    name = "apps.billing"
    verbose_name = "Assinaturas e pagamentos"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa
