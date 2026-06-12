import logging

from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from .models.v2 import Integration, IntegrationConfiguration, RouteProvider

logger = logging.getLogger(__name__)


# IntegrationAction post-save backfill lives on the model itself
# (IntegrationAction._post_save in models/v2/models.py) to match the codebase
# convention for v2 model lifecycle hooks. The pre_delete receiver below stays
# here because the periodic-task cleanup tied to historical-model deletes
# needs to fire on signal dispatch, not the model save() path.


@receiver(pre_delete, sender=IntegrationConfiguration)
def on_integration_config_delete(sender, **kwargs):
    config = kwargs.get("instance")
    if config and config.periodic_task:
        config.periodic_task.delete()


@receiver(post_delete, sender=RouteProvider)
def disable_pull_tasks_when_no_longer_a_provider(sender, **kwargs):
    """Pause scheduled pull actions when an integration stops being a provider.

    `RouteProvider._post_save` enables an integration's periodic pull tasks when
    it's added as a provider to a route. This is the mirror image: when a
    provider link is removed (route edited via `data_providers.set(...)`, or the
    route deleted), disable those tasks if the integration is no longer a
    provider in ANY route — otherwise they keep firing pull_events /
    pull_observations on what is now a destination-only integration. See
    GUNDI-5400.

    A signal (rather than RouteProvider.delete()) is used because removals go
    through `QuerySet.delete()` on the through model, which bypasses the
    model's delete() but still dispatches post_delete.
    """
    instance = kwargs.get("instance")
    if not instance:
        return
    try:
        integration = Integration.objects.get(pk=instance.integration_id)
    except Integration.DoesNotExist:
        # The integration itself was deleted (cascade) — its tasks go with it.
        return
    if integration.is_used_as_provider:
        # Still a provider via another route; leave the tasks enabled.
        return
    for config in integration.periodic_pull_action_configurations:
        if config.periodic_task and config.periodic_task.enabled:
            config.periodic_task.enabled = False
            config.periodic_task.save()
