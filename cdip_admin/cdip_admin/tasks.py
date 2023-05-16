import logging

import redis
from celery_once import QueueOnce
from django.conf import settings

from cdip_admin import celery
from integrations.models import OutboundIntegrationConfiguration

from sync_integrations.utils import (
    run_er_smart_sync_integrations,
    on_smart_integration_save,
)

logger = logging.getLogger(__name__)

# This is a sentinel key that a livenessProbe will look for to determine health of celery beat.
CELERYBEAT_PULSE_SENTINEL_KEY = "celerybeat-pulse-sentinel"


@celery.app.task(base=QueueOnce, once={"graceful": True})
def celerybeat_pulse():
    """
    Set a sentinel key to expire in 120 seconds.
    :return: None
    """
    redis_client = redis.from_url(settings.CELERY_BROKER_URL)
    redis_client.setex(CELERYBEAT_PULSE_SENTINEL_KEY, 30, "n/a")


@celery.app.task(base=QueueOnce, once={"graceful": True})
def run_sync_integrations():
    run_er_smart_sync_integrations()


@celery.app.task(base=QueueOnce, once={"graceful": True})
def handle_outboundintegration_save(integration_id):

    try:
        oic = OutboundIntegrationConfiguration.objects.get(id=integration_id)
    except OutboundIntegrationConfiguration.DoesNotExist:
        logger.error(f'OutboundIntegrationConfiguration(%s) does not exist.', integration_id)
    else:

        if oic.type.slug == 'smart_connect':
            on_smart_integration_save(integration_id=integration_id)
