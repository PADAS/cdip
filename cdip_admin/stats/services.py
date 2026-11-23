"""
Aggregation of hourly stats rollups from GundiTrace and ActivityLog.

Rules that keep the load on the shared database bounded:
- every query on a source table is a one-hour range scan on an indexed
  timestamp column;
- every bucket runs under a transaction-local statement timeout;
- a bucket is replaced as a whole (delete + insert in one transaction), so a
  rerun is idempotent and a count that dropped to zero disappears.
"""
import dataclasses
import datetime
import logging

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count, Q
from django.utils import timezone

from activity_log.models import ActivityLog
from event_consumers.dispatcher_events_consumer import DELIVERY_FAILED_TRACE_ERROR
from integrations.models import GundiTrace

from .models import ErrorRollup, RollupRunState, ThroughputRollup

logger = logging.getLogger(__name__)

HOUR = datetime.timedelta(hours=1)

# Failures the dispatcher logs at WARNING when it will retry them. They are
# stored next to the errors so they can be reported separately on request.
RETRIABLE_FAILURE_VALUES = ("observation_delivery_failed", "observation_update_failed")

FREQUENT_RUN = "frequent"
DAILY_RUN = "daily"
_RUN_STATE_FIELDS = {
    FREQUENT_RUN: "frequent_run_completed_at",
    DAILY_RUN: "daily_run_completed_at",
}


@dataclasses.dataclass
class AggregationResult:
    aggregated: list = dataclasses.field(default_factory=list)
    # Buckets whose throughput was left untouched because they start before
    # the per-destination copy flag is reliable (or the start is not set).
    skipped_throughput: list = dataclasses.field(default_factory=list)
    # Buckets whose errors were left untouched because the activity log no
    # longer holds that hour.
    skipped_errors: list = dataclasses.field(default_factory=list)
    # Buckets that raised; they keep their previous rows.
    failed: list = dataclasses.field(default_factory=list)


def floor_to_hour(moment):
    return moment.astimezone(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)


def hour_buckets(start, end):
    """Hour buckets that overlap [start, end)."""
    buckets = []
    bucket = floor_to_hour(start)
    while bucket < end:
        buckets.append(bucket)
        bucket += HOUR
    return buckets


def trailing_buckets(hours, now=None):
    """The current hour and the hours before it, oldest first."""
    current = floor_to_hour(now or timezone.now())
    return [current - HOUR * offset for offset in range(hours - 1, -1, -1)]


def _validate_bucket(bucket):
    if timezone.is_naive(bucket):
        raise ValueError(f"Bucket {bucket!r} must be timezone-aware.")
    if bucket != floor_to_hour(bucket):
        raise ValueError(f"Bucket {bucket!r} must be the start of an hour.")


def _count_received(start, end):
    # Rows the consumers add for an additional destination are created at
    # delivery time and are not new items, so they are not received.
    return (
        GundiTrace.objects.order_by()
        .filter(created_at__gte=start, created_at__lt=end)
        .exclude(is_destination_copy=True)
        .values("data_provider_id", "object_type")
        .annotate(
            received=Count("id"),
            duplicate=Count("id", filter=Q(is_duplicate=True)),
        )
    )


def _count_delivered(start, end):
    # The delivery-failed handler stores the dispatcher's timestamp in
    # delivered_at on the row it creates, so that row is not a delivery. A row
    # whose later update failed also has has_error set, and stays delivered.
    return (
        GundiTrace.objects.order_by()
        .filter(delivered_at__gte=start, delivered_at__lt=end)
        .exclude(has_error=True, error=DELIVERY_FAILED_TRACE_ERROR)
        .values("data_provider_id", "destination_id", "object_type")
        .annotate(n=Count("id"))
    )


def _count_discarded(start, end):
    return (
        GundiTrace.objects.order_by()
        .filter(discarded_at__gte=start, discarded_at__lt=end)
        .values("data_provider_id", "destination_id", "object_type")
        .annotate(n=Count("id"))
    )


def _count_errors(start, end):
    levels = ActivityLog.LogLevels
    return (
        ActivityLog.objects.order_by()
        .filter(created_at__gte=start, created_at__lt=end)
        .filter(
            Q(log_level=levels.ERROR)
            | Q(log_level=levels.WARNING, value__in=RETRIABLE_FAILURE_VALUES)
        )
        .values("integration_id", "origin", "value", "log_level")
        .annotate(n=Count("id"))
    )


def _throughput_rows(bucket):
    end = bucket + HOUR
    Metric = ThroughputRollup.Metric
    rows = []

    def add(metric, count, group, destination_id=None):
        if count:
            rows.append(ThroughputRollup(
                bucket=bucket,
                data_provider_id=group["data_provider_id"],
                destination_id=destination_id,
                object_type=group["object_type"],
                metric=metric,
                count=count,
            ))

    for group in _count_received(bucket, end):
        add(Metric.RECEIVED, group["received"], group)
        add(Metric.DUPLICATE, group["duplicate"], group)
    for group in _count_delivered(bucket, end):
        add(Metric.DELIVERED, group["n"], group, group["destination_id"])
    for group in _count_discarded(bucket, end):
        add(Metric.DISCARDED, group["n"], group, group["destination_id"])
    return rows


def _error_rows(bucket):
    return [
        ErrorRollup(
            bucket=bucket,
            integration_id=group["integration_id"],
            origin=group["origin"],
            value=group["value"],
            log_level=group["log_level"],
            count=group["n"],
        )
        for group in _count_errors(bucket, bucket + HOUR)
    ]


# Arbitrary constant identifying "stats rollup bucket replacement" among
# PostgreSQL advisory locks.
_ADVISORY_LOCK_KEY = 5_810_001


def _prepare_bucket_transaction():
    timeout_ms = int(settings.STATS_ROLLUP_STATEMENT_TIMEOUT_MS)
    with connection.cursor() as cursor:
        # The frequent task, the daily reconcile and the rebuild command can
        # all replace the same bucket. Without this lock the second writer's
        # DELETE misses the first one's uncommitted rows and its INSERT then
        # violates the unique constraints. Released at the end of the transaction.
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_ADVISORY_LOCK_KEY])
        # The database has no global statement_timeout. SET LOCAL lasts until
        # the end of the surrounding transaction. It is set after taking the
        # lock so that waiting for another run is not cut short by it.
        cursor.execute("SET LOCAL statement_timeout = %s", [timeout_ms])


def aggregate_buckets(buckets, now=None):
    """
    Recompute the rollups of the given hour buckets.

    A bucket that fails keeps its previous rows and does not stop the others:
    one hour that keeps hitting the statement timeout must not starve the
    hours after it. If any bucket failed, the first error is raised after the
    loop, and the caller must treat the run as failed.
    """
    now = now or timezone.now()
    throughput_start = settings.STATS_THROUGHPUT_START
    errors_start = now - datetime.timedelta(days=settings.STATS_ERROR_SOURCE_RETENTION_DAYS)
    result = AggregationResult()
    first_error = None

    for bucket in buckets:
        _validate_bucket(bucket)
        with_throughput = throughput_start is not None and bucket >= throughput_start
        with_errors = bucket >= errors_start
        if not with_throughput:
            result.skipped_throughput.append(bucket)
        if not with_errors:
            result.skipped_errors.append(bucket)
        if not (with_throughput or with_errors):
            continue

        try:
            with transaction.atomic():
                _prepare_bucket_transaction()
                if with_throughput:
                    rows = _throughput_rows(bucket)
                    ThroughputRollup.objects.filter(bucket=bucket).delete()
                    ThroughputRollup.objects.bulk_create(rows)
                if with_errors:
                    rows = _error_rows(bucket)
                    ErrorRollup.objects.filter(bucket=bucket).delete()
                    ErrorRollup.objects.bulk_create(rows)
        except Exception as error:
            logger.exception("Stats rollup failed for bucket %s.", bucket.isoformat())
            result.failed.append(bucket)
            first_error = first_error or error
            continue
        result.aggregated.append(bucket)

    if result.skipped_throughput and throughput_start is None:
        logger.warning(
            "STATS_THROUGHPUT_START is not set: throughput was not aggregated for %d bucket(s).",
            len(result.skipped_throughput),
        )
    if first_error is not None:
        raise first_error
    return result


def run_rollup(run, hours, now=None):
    """Aggregate the trailing window of a scheduled run and record its success."""
    buckets = trailing_buckets(hours, now=now)
    field = _RUN_STATE_FIELDS[run]
    previous = getattr(RollupRunState.load(), field)
    if previous is not None and previous < buckets[0]:
        # The job was stopped or failing for longer than its window. The hours
        # in between are not aggregated by any scheduled run.
        logger.warning(
            "Stats rollup (%s) last succeeded at %s, before its %d-hour window. Hours from then to %s "
            "are not covered: run rebuild_stats_rollups for that range.",
            run, previous.isoformat(), hours, buckets[0].isoformat(),
        )
    result = aggregate_buckets(buckets, now=now)
    # Only reached when every bucket succeeded.
    RollupRunState.objects.filter(pk=RollupRunState.SINGLETON_PK).update(**{field: timezone.now()})
    return result
