from django.apps import AppConfig


class StoresConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.stores'

    def ready(self):
        pass
       # import apps.stores.signals
