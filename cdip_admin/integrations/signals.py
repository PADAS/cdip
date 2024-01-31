from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models.v2 import IntegrationConfiguration


@receiver(pre_delete, sender=IntegrationConfiguration)
def on_integration_config_delete(sender, **kwargs):
    config = kwargs.get("instance")
    if config and config.periodic_task:
        config.periodic_task.delete()
