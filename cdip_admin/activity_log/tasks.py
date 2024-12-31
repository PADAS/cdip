import json
import logging
from celery import shared_task
from django.db import ProgrammingError, connection
from django.conf import settings

from core.utils import get_publisher

logger = logging.getLogger(__name__)

publisher = get_publisher()


@shared_task
def run_partitions_maintenance():
    """
    Runs the partman partition maintenance procedure.
    This will detach old partitions and create new ones as needed.
    """
    with connection.cursor() as cursor:
        try:
            logger.info(f"Running partman.run_maintenance_proc()...")
            cursor.execute("CALL partman.run_maintenance_proc();")
        except ProgrammingError as e:
            logger.exception("Error running partman.run_maintenance_proc()")
        else:
            logger.info("partman.run_maintenance_proc() completed.")


@shared_task(autoretry_for=(Exception,), retry_backoff=10, retry_kwargs={'max_retries': 5})
def publish_configuration_event(event_data: dict, topic: str = settings.CONFIGURATION_EVENTS_TOPIC):
    publisher.publish(
        topic=topic,
        data=event_data,
        ordering_key="config-event",  # Data changes must be processed in order
        extra={
            "gundi_version": "v2",
            "event_type": event_data["event_type"],  # Used for filtering in subscriptions
        },
    )
