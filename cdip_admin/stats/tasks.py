import logging

from celery import shared_task
from celery_once import QueueOnce
from django.conf import settings

from . import services

logger = logging.getLogger(__name__)


def _run(run, hours):
    result = services.run_rollup(run, hours)
    logger.info(
        "Stats rollup (%s) aggregated %d bucket(s); skipped throughput for %d, errors for %d.",
        run, len(result.aggregated), len(result.skipped_throughput), len(result.skipped_errors),
    )
    return len(result.aggregated)


@shared_task(base=QueueOnce, once={"graceful": True})
def refresh_recent_stats_rollups():
    """Recompute the current and previous hours. Runs every few minutes."""
    return _run(services.FREQUENT_RUN, settings.STATS_ROLLUP_FREQUENT_HOURS)


# The reconcile covers many more buckets than the default three-minute lock.
@shared_task(base=QueueOnce, once={"graceful": True, "timeout": 60 * 60})
def reconcile_stats_rollups():
    """Recompute the trailing window to pick up late deliveries. Runs daily."""
    return _run(services.DAILY_RUN, settings.STATS_ROLLUP_RECONCILE_HOURS)
