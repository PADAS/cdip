import logging

import redis
from celery_once import QueueOnce
from django.conf import settings

from cdip_admin import celery
from sync_integrations.utils import run_er_smart_sync_integrations

logger = logging.getLogger(__name__)

# This is a sentinel key that a livenessProbe will look for to determine health of celery beat.
CELERYBEAT_PULSE_SENTINEL_KEY = 'celerybeat-pulse-sentinel'


@celery.app.task(base=QueueOnce, once={'graceful': True})
def celerybeat_pulse():
    '''
    Set a sentinel key to expire in 120 seconds.
    :return: None
    '''
    redis_client = redis.from_url(settings.CELERY_BROKER_URL)
    redis_client.setex(CELERYBEAT_PULSE_SENTINEL_KEY, 30, 'n/a')
