import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .models.v2 import IntegrationAction, IntegrationConfiguration
from .tasks import backfill_action_configurations_for_type

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=IntegrationConfiguration)
def on_integration_config_delete(sender, **kwargs):
    config = kwargs.get("instance")
    if config and config.periodic_task:
        config.periodic_task.delete()


@receiver(post_save, sender=IntegrationAction)
def backfill_configurations_for_new_action(sender, instance, created, **kwargs):
    # When a new IntegrationAction is added to an IntegrationType, every existing
    # Integration of that type is missing a configuration row for it. Dispatch
    # the backfill to a Celery worker so action creation isn't blocked by an
    # O(integrations × actions) loop in the request thread.
    if not created:
        return

    integration_type_id = instance.integration_type_id

    transaction.on_commit(
        lambda: backfill_action_configurations_for_type.delay(str(integration_type_id))
    )
