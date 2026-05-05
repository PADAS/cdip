import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .models.v2 import Integration, IntegrationAction, IntegrationConfiguration

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=IntegrationConfiguration)
def on_integration_config_delete(sender, **kwargs):
    config = kwargs.get("instance")
    if config and config.periodic_task:
        config.periodic_task.delete()


@receiver(post_save, sender=IntegrationAction)
def backfill_configurations_for_new_action(sender, instance, created, **kwargs):
    # When a new IntegrationAction is added to an IntegrationType, every existing
    # Integration of that type is missing a configuration row for it. Backfill
    # them so admins don't have to repair by hand.
    if not created:
        return

    integration_type_id = instance.integration_type_id

    def _backfill():
        integrations = Integration.objects.filter(type_id=integration_type_id)
        for integration in integrations.iterator():
            integration.create_missing_configurations()

    transaction.on_commit(_backfill)
