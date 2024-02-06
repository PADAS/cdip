from django.apps import AppConfig


class DevicesConfig(AppConfig):
    name = "integrations"

    def ready(self):
        from . import signals
