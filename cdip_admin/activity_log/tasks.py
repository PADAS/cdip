import logging
from celery import shared_task
from django.db import ProgrammingError, connection


logger = logging.getLogger(__name__)


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
