import logging

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models.v2 import IntegrationConfiguration

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
