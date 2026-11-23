import datetime
import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from activity_log.models import ActivityLog
from event_consumers.dispatcher_events_consumer import (
    DELIVERY_FAILED_TRACE_ERROR,
    UPDATE_FAILED_TRACE_ERROR,
)
from integrations.models import GundiTrace
from stats import services
from stats.models import ErrorRollup, ThroughputRollup

pytestmark = pytest.mark.django_db

UTC = datetime.timezone.utc
HOUR = datetime.timedelta(hours=1)
BUCKET = datetime.datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
NOW = BUCKET + datetime.timedelta(hours=1, minutes=5)
Metric = ThroughputRollup.Metric


@pytest.fixture(autouse=True)
def stats_settings(settings):
    settings.STATS_THROUGHPUT_START = BUCKET - datetime.timedelta(days=30)
    settings.STATS_ERROR_SOURCE_RETENTION_DAYS = 20
    return settings


def make_trace(provider, *, created_at=None, object_type="obv", **fields):
    trace = GundiTrace.objects.create(
        data_provider=provider, object_type=object_type, **fields
    )
    # created_at is auto_now_add, so it can only be set after the insert.
    GundiTrace.objects.filter(pk=trace.pk).update(
        created_at=created_at or BUCKET + datetime.timedelta(minutes=10)
    )
    return trace


def make_log(integration, *, value, level=ActivityLog.LogLevels.ERROR,
             origin=ActivityLog.Origin.DISPATCHER, created_at=None):
    log = ActivityLog.objects.create(
        log_level=level,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=origin,
        integration=integration,
        value=value,
        title="A failure",
    )
    ActivityLog.objects.filter(pk=log.pk).update(
        created_at=created_at or BUCKET + datetime.timedelta(minutes=10)
    )
    return log


def throughput(metric, **filters):
    rows = ThroughputRollup.objects.filter(metric=metric, **filters)
    return sum(row.count for row in rows)


def errors(**filters):
    return sum(row.count for row in ErrorRollup.objects.filter(**filters))


def aggregate(buckets=(BUCKET,), now=NOW):
    return services.aggregate_buckets(list(buckets), now=now)


# --- buckets ----------------------------------------------------------------

def test_hour_buckets_cover_a_range_from_the_start_of_its_first_hour():
    start = BUCKET + datetime.timedelta(minutes=40)
    end = BUCKET + datetime.timedelta(hours=2, minutes=1)
    assert services.hour_buckets(start, end) == [BUCKET, BUCKET + HOUR, BUCKET + 2 * HOUR]


def test_hour_buckets_exclude_an_hour_that_starts_at_the_end():
    assert services.hour_buckets(BUCKET, BUCKET + HOUR) == [BUCKET]


def test_trailing_buckets_end_with_the_current_hour():
    assert services.trailing_buckets(2, now=NOW) == [BUCKET, BUCKET + HOUR]


# --- throughput -------------------------------------------------------------

def test_received_is_counted_per_provider_data_type_and_bucket(
    provider_lotek_panthera, provider_trap_tagger
):
    make_trace(provider_lotek_panthera)
    make_trace(provider_lotek_panthera)
    make_trace(provider_lotek_panthera, object_type="ev")
    make_trace(provider_trap_tagger)
    make_trace(provider_lotek_panthera, created_at=BUCKET + HOUR)  # next bucket
    make_trace(provider_lotek_panthera, created_at=BUCKET - datetime.timedelta(seconds=1))

    aggregate()

    received = {
        (row.data_provider_id, row.object_type): row.count
        for row in ThroughputRollup.objects.filter(metric=Metric.RECEIVED)
    }
    assert received == {
        (provider_lotek_panthera.id, "obv"): 2,
        (provider_lotek_panthera.id, "ev"): 1,
        (provider_trap_tagger.id, "obv"): 1,
    }
    assert all(
        row.bucket == BUCKET and row.destination_id is None
        for row in ThroughputRollup.objects.filter(metric=Metric.RECEIVED)
    )


def test_destination_copy_counts_as_delivered_and_not_as_received(
    provider_lotek_panthera, integrations_list_er
):
    first, second = integrations_list_er[0], integrations_list_er[1]
    delivered_at = BUCKET + datetime.timedelta(minutes=20)
    make_trace(provider_lotek_panthera, destination=first, delivered_at=delivered_at)
    make_trace(
        provider_lotek_panthera, destination=second, delivered_at=delivered_at,
        is_destination_copy=True,
    )

    aggregate()

    assert throughput(Metric.RECEIVED) == 1
    assert throughput(Metric.DELIVERED) == 2
    assert throughput(Metric.DELIVERED, destination_id=first.id) == 1
    assert throughput(Metric.DELIVERED, destination_id=second.id) == 1


def test_failed_delivery_row_is_not_counted_as_delivered(
    provider_lotek_panthera, integrations_list_er
):
    # The delivery-failed handler copies the dispatcher's timestamp into
    # delivered_at on the row it creates for an additional destination.
    make_trace(
        provider_lotek_panthera, destination=integrations_list_er[0],
        delivered_at=BUCKET + datetime.timedelta(minutes=20),
        has_error=True, error=DELIVERY_FAILED_TRACE_ERROR, is_destination_copy=True,
    )

    aggregate()

    assert throughput(Metric.DELIVERED) == 0


def test_delivered_item_whose_later_update_failed_still_counts_as_delivered(
    provider_lotek_panthera, integrations_list_er
):
    make_trace(
        provider_lotek_panthera, destination=integrations_list_er[0],
        delivered_at=BUCKET + datetime.timedelta(minutes=20),
        has_error=True, error=UPDATE_FAILED_TRACE_ERROR,
    )

    aggregate()

    assert throughput(Metric.DELIVERED) == 1


@pytest.mark.parametrize("error", [None, ""])
def test_delivered_row_without_error_text_counts_as_delivered(
    provider_lotek_panthera, integrations_list_er, error
):
    make_trace(
        provider_lotek_panthera, destination=integrations_list_er[0],
        delivered_at=BUCKET + datetime.timedelta(minutes=20), error=error,
    )

    aggregate()

    assert throughput(Metric.DELIVERED) == 1


def test_delivered_is_counted_in_the_bucket_of_delivery_not_of_receipt(
    provider_lotek_panthera, integrations_list_er
):
    make_trace(
        provider_lotek_panthera, destination=integrations_list_er[0],
        created_at=BUCKET - datetime.timedelta(minutes=5),
        delivered_at=BUCKET + datetime.timedelta(minutes=1),
    )

    aggregate([BUCKET - HOUR, BUCKET])

    assert throughput(Metric.RECEIVED, bucket=BUCKET - HOUR) == 1
    assert throughput(Metric.DELIVERED, bucket=BUCKET - HOUR) == 0
    assert throughput(Metric.DELIVERED, bucket=BUCKET) == 1


def test_duplicate_counts_as_received_and_as_duplicate(provider_lotek_panthera):
    make_trace(provider_lotek_panthera)
    make_trace(provider_lotek_panthera, is_duplicate=True)

    aggregate()

    assert throughput(Metric.RECEIVED) == 2
    assert throughput(Metric.DUPLICATE) == 1


def test_discarded_is_counted_in_the_bucket_of_discarded_at(
    provider_lotek_panthera, integrations_list_er
):
    make_trace(
        provider_lotek_panthera, destination=integrations_list_er[0],
        created_at=BUCKET - datetime.timedelta(minutes=5),
        discarded_at=BUCKET + datetime.timedelta(minutes=1),
    )

    aggregate([BUCKET - HOUR, BUCKET])

    assert throughput(Metric.DISCARDED, bucket=BUCKET - HOUR) == 0
    assert throughput(Metric.DISCARDED, bucket=BUCKET) == 1
    assert throughput(Metric.DISCARDED, destination_id=integrations_list_er[0].id) == 1
    assert throughput(Metric.DELIVERED) == 0


def test_late_delivery_appears_after_the_next_run_covering_its_hour(
    provider_lotek_panthera, integrations_list_er
):
    trace = make_trace(provider_lotek_panthera)
    aggregate()
    assert throughput(Metric.DELIVERED) == 0

    GundiTrace.objects.filter(pk=trace.pk).update(
        destination=integrations_list_er[0],
        delivered_at=BUCKET + datetime.timedelta(minutes=30),
    )
    aggregate()

    assert throughput(Metric.DELIVERED) == 1
    assert throughput(Metric.RECEIVED) == 1


def test_running_twice_on_the_same_buckets_leaves_the_same_rows(
    provider_lotek_panthera, integrations_list_er
):
    make_trace(provider_lotek_panthera, is_duplicate=True)
    make_trace(
        provider_lotek_panthera, destination=integrations_list_er[0],
        delivered_at=BUCKET + datetime.timedelta(minutes=30),
    )
    make_log(provider_lotek_panthera, value="observation_delivery_failed")

    def snapshot():
        return (
            sorted(ThroughputRollup.objects.values_list(
                "bucket", "data_provider_id", "destination_id", "object_type", "metric", "count"), key=str),
            sorted(ErrorRollup.objects.values_list(
                "bucket", "integration_id", "origin", "value", "log_level", "count"), key=str),
        )

    aggregate()
    first = snapshot()
    aggregate()

    assert snapshot() == first
    assert first[0] and first[1]


def test_count_that_drops_to_zero_removes_its_row(provider_lotek_panthera):
    trace = make_trace(provider_lotek_panthera)
    log = make_log(provider_lotek_panthera, value="observation_delivery_failed")
    aggregate()
    assert ThroughputRollup.objects.exists() and ErrorRollup.objects.exists()

    trace.delete()
    ActivityLog.objects.filter(pk=log.pk).delete()
    aggregate()

    assert not ThroughputRollup.objects.exists()
    assert not ErrorRollup.objects.exists()


def test_buckets_outside_the_run_are_left_alone(provider_lotek_panthera):
    other = ThroughputRollup.objects.create(
        bucket=BUCKET - 5 * HOUR, data_provider_id=provider_lotek_panthera.id,
        object_type="obv", metric=Metric.RECEIVED, count=7,
    )

    aggregate()

    assert ThroughputRollup.objects.filter(pk=other.pk, count=7).exists()


def test_throughput_bucket_before_the_flag_start_is_not_aggregated(
    provider_lotek_panthera, stats_settings
):
    stats_settings.STATS_THROUGHPUT_START = BUCKET + datetime.timedelta(minutes=30)
    make_trace(provider_lotek_panthera)
    make_trace(provider_lotek_panthera, created_at=BUCKET + HOUR + datetime.timedelta(minutes=1))
    make_log(provider_lotek_panthera, value="observation_delivery_failed")

    result = aggregate([BUCKET, BUCKET + HOUR], now=BUCKET + 2 * HOUR)

    # The bucket starts before the flag is reliable, even though it ends after.
    assert throughput(Metric.RECEIVED, bucket=BUCKET) == 0
    assert throughput(Metric.RECEIVED, bucket=BUCKET + HOUR) == 1
    assert result.skipped_throughput == [BUCKET]
    # Errors do not depend on the flag.
    assert errors(bucket=BUCKET) == 1


def test_throughput_is_not_aggregated_when_the_flag_start_is_unset(
    provider_lotek_panthera, stats_settings
):
    stats_settings.STATS_THROUGHPUT_START = None
    make_trace(provider_lotek_panthera)

    result = aggregate()

    assert not ThroughputRollup.objects.exists()
    assert result.skipped_throughput == [BUCKET]


# --- errors -----------------------------------------------------------------

@pytest.mark.parametrize("value,origin", [
    ("integration_action_failed", ActivityLog.Origin.INTEGRATION),
    ("integration_webhook_failed", ActivityLog.Origin.INTEGRATION),
    ("observation_delivery_failed", ActivityLog.Origin.DISPATCHER),
    ("observation_update_failed", ActivityLog.Origin.DISPATCHER),
])
def test_error_logs_are_counted_by_integration_origin_and_value(
    provider_lotek_panthera, value, origin
):
    make_log(provider_lotek_panthera, value=value, origin=origin)
    make_log(provider_lotek_panthera, value=value, origin=origin)

    aggregate()

    row = ErrorRollup.objects.get()
    assert (row.bucket, row.integration_id, row.origin, row.value, row.log_level, row.count) == (
        BUCKET, provider_lotek_panthera.id, origin, value, ActivityLog.LogLevels.ERROR, 2
    )


def test_warning_delivery_failure_is_stored_with_its_level(provider_lotek_panthera):
    make_log(provider_lotek_panthera, value="observation_delivery_failed")
    make_log(
        provider_lotek_panthera, value="observation_delivery_failed",
        level=ActivityLog.LogLevels.WARNING,
    )

    aggregate()

    assert errors(log_level=ActivityLog.LogLevels.ERROR) == 1
    assert errors(log_level=ActivityLog.LogLevels.WARNING) == 1


def test_warnings_that_are_not_retriable_failures_and_lower_levels_are_ignored(
    provider_lotek_panthera
):
    make_log(provider_lotek_panthera, value="some_custom_warning", level=ActivityLog.LogLevels.WARNING)
    make_log(provider_lotek_panthera, value="observation_delivery_succeeded", level=ActivityLog.LogLevels.DEBUG)
    make_log(provider_lotek_panthera, value="integration_updated", level=ActivityLog.LogLevels.INFO)

    aggregate()

    assert not ErrorRollup.objects.exists()


def test_error_log_without_integration_is_stored_under_a_null_integration():
    make_log(None, value="integration_action_failed", origin=ActivityLog.Origin.INTEGRATION)

    aggregate()

    row = ErrorRollup.objects.get()
    assert row.integration_id is None and row.count == 1


def test_error_log_outside_the_bucket_is_not_counted(provider_lotek_panthera):
    make_log(provider_lotek_panthera, value="observation_delivery_failed", created_at=BUCKET + HOUR)

    aggregate()

    assert not ErrorRollup.objects.exists()


def test_error_buckets_older_than_source_retention_keep_their_rows(provider_lotek_panthera):
    old_bucket = BUCKET - datetime.timedelta(days=25)
    kept = ErrorRollup.objects.create(
        bucket=old_bucket, integration_id=provider_lotek_panthera.id, origin="disp",
        value="observation_delivery_failed", log_level=40, count=9,
    )
    make_trace(provider_lotek_panthera, created_at=old_bucket + datetime.timedelta(minutes=5))

    result = aggregate([old_bucket])

    # The activity log no longer holds that hour: replacing would erase history.
    assert ErrorRollup.objects.filter(pk=kept.pk, count=9).exists()
    assert result.skipped_errors == [old_bucket]
    # Traces are not subject to that retention.
    assert throughput(Metric.RECEIVED, bucket=old_bucket) == 1


# --- failure and load -------------------------------------------------------

def test_failed_bucket_fails_the_run_and_keeps_its_previous_rows(provider_lotek_panthera, mocker):
    make_trace(provider_lotek_panthera)
    aggregate()
    make_trace(provider_lotek_panthera)
    mocker.patch.object(services, "_count_errors", side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        aggregate()

    # The bucket is replaced in one transaction: a failure keeps the old counts.
    assert throughput(Metric.RECEIVED) == 1


def test_bucket_must_be_an_aware_hour_start():
    with pytest.raises(ValueError):
        aggregate([BUCKET + datetime.timedelta(minutes=1)])
    with pytest.raises(ValueError):
        aggregate([BUCKET.replace(tzinfo=None)])


def test_every_source_query_is_bounded_by_a_time_range_on_an_indexed_column(
    provider_lotek_panthera, integrations_list_er
):
    make_trace(provider_lotek_panthera)
    make_log(provider_lotek_panthera, value="observation_delivery_failed")

    with CaptureQueriesContext(connection) as queries:
        aggregate()

    statements = [q["sql"] for q in queries]
    trace_selects = [s for s in statements if s.startswith("SELECT") and "integrations_gunditrace" in s]
    log_selects = [s for s in statements if s.startswith("SELECT") and "activity_log_activitylog" in s]
    assert len(trace_selects) == 3 and len(log_selects) == 1
    indexed_ranges = ('"created_at" >=', '"delivered_at" >=', '"discarded_at" >=')
    for sql in trace_selects + log_selects:
        assert any(marker in sql for marker in indexed_ranges), sql
    assert any("statement_timeout" in s for s in statements)
