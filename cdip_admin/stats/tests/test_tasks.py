import datetime
import importlib
from io import StringIO

import pytest
from django.conf import settings as django_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django_celery_beat.models import PeriodicTask

from integrations.models import GundiTrace
from stats import services, tasks
from stats.models import ErrorRollup, RollupRunState, ThroughputRollup

pytestmark = pytest.mark.django_db

UTC = datetime.timezone.utc
HOUR = datetime.timedelta(hours=1)
FREQUENT_TASK = "stats.tasks.refresh_recent_stats_rollups"
DAILY_TASK = "stats.tasks.reconcile_stats_rollups"


@pytest.fixture(autouse=True)
def stats_settings(settings):
    settings.STATS_THROUGHPUT_START = datetime.datetime(2020, 1, 1, tzinfo=UTC)
    return settings


# --- schedule ---------------------------------------------------------------

def test_migration_creates_both_periodic_tasks_disabled():
    frequent = PeriodicTask.objects.get(task=FREQUENT_TASK)
    daily = PeriodicTask.objects.get(task=DAILY_TASK)

    assert frequent.enabled is False and daily.enabled is False
    assert frequent.crontab.minute == "*/10" and frequent.crontab.hour == "*"
    assert (daily.crontab.minute, daily.crontab.hour) == ("30", "3")


def test_schedule_migration_is_idempotent_and_keeps_an_operator_change():
    from django.apps import apps as django_apps

    migration = importlib.import_module("stats.migrations.0002_rollup_schedule")
    PeriodicTask.objects.filter(task=FREQUENT_TASK).update(enabled=True)

    migration.create_rollup_schedule(django_apps, None)

    assert PeriodicTask.objects.filter(task__in=[FREQUENT_TASK, DAILY_TASK]).count() == 2
    assert PeriodicTask.objects.get(task=FREQUENT_TASK).enabled is True

    migration.delete_rollup_schedule(django_apps, None)
    assert not PeriodicTask.objects.filter(task__in=[FREQUENT_TASK, DAILY_TASK]).exists()


def test_tasks_are_registered_under_the_scheduled_names_on_the_healthchecks_queue():
    assert tasks.refresh_recent_stats_rollups.name == FREQUENT_TASK
    assert tasks.reconcile_stats_rollups.name == DAILY_TASK
    for name in (FREQUENT_TASK, DAILY_TASK):
        assert django_settings.CELERY_TASK_ROUTES[name]["queue"] == "healthchecks"


# --- runs -------------------------------------------------------------------

def test_frequent_task_aggregates_the_current_and_previous_hour(provider_lotek_panthera):
    now = datetime.datetime.now(UTC)
    current = services.floor_to_hour(now)
    for created_at in (now, current - datetime.timedelta(minutes=1), current - 3 * HOUR):
        trace = GundiTrace.objects.create(data_provider=provider_lotek_panthera, object_type="obv")
        GundiTrace.objects.filter(pk=trace.pk).update(created_at=created_at)

    tasks.refresh_recent_stats_rollups.run()

    buckets = set(ThroughputRollup.objects.values_list("bucket", flat=True))
    assert buckets == {current, current - HOUR}


def test_daily_task_aggregates_the_reconcile_window(provider_lotek_panthera, stats_settings):
    stats_settings.STATS_ROLLUP_RECONCILE_HOURS = 48
    current = services.floor_to_hour(datetime.datetime.now(UTC))
    for created_at in (current - 47 * HOUR, current - 48 * HOUR - datetime.timedelta(minutes=1)):
        trace = GundiTrace.objects.create(data_provider=provider_lotek_panthera, object_type="obv")
        GundiTrace.objects.filter(pk=trace.pk).update(created_at=created_at)

    tasks.reconcile_stats_rollups.run()

    assert set(ThroughputRollup.objects.values_list("bucket", flat=True)) == {current - 47 * HOUR}


def test_frequent_and_daily_tasks_advance_separate_run_state_times():
    before = datetime.datetime.now(UTC)

    tasks.refresh_recent_stats_rollups.run()

    state = RollupRunState.load()
    assert state.frequent_run_completed_at >= before
    assert state.daily_run_completed_at is None

    tasks.reconcile_stats_rollups.run()

    state.refresh_from_db()
    assert state.daily_run_completed_at >= state.frequent_run_completed_at


def test_failed_run_does_not_advance_the_run_state(mocker):
    tasks.refresh_recent_stats_rollups.run()
    succeeded_at = RollupRunState.load().frequent_run_completed_at
    current = services.floor_to_hour(datetime.datetime.now(UTC))
    real = services._error_rows

    def fail_on_current_hour(bucket):
        if bucket == current:
            raise RuntimeError("boom")
        return real(bucket)

    # One of the two buckets fails: the whole run is a failed run.
    mocker.patch.object(services, "_error_rows", side_effect=fail_on_current_hour)

    with pytest.raises(RuntimeError):
        tasks.refresh_recent_stats_rollups.run()

    assert RollupRunState.load().frequent_run_completed_at == succeeded_at


# --- rebuild command --------------------------------------------------------

def test_rebuild_command_aggregates_the_given_range(provider_lotek_panthera):
    bucket = datetime.datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
    trace = GundiTrace.objects.create(data_provider=provider_lotek_panthera, object_type="obv")
    GundiTrace.objects.filter(pk=trace.pk).update(created_at=bucket + datetime.timedelta(minutes=5))
    out = StringIO()

    call_command(
        "rebuild_stats_rollups", "--from", "2026-11-20T14:00:00Z", "--to", "2026-11-20T16:00:00Z", stdout=out
    )

    assert ThroughputRollup.objects.get().bucket == bucket
    assert "2 hour bucket(s)" in out.getvalue()
    # A manual rebuild is not a scheduled run.
    assert RollupRunState.load().frequent_run_completed_at is None


def test_rebuild_command_keeps_and_reports_error_buckets_older_than_retention(provider_lotek_panthera):
    old = services.floor_to_hour(datetime.datetime.now(UTC) - datetime.timedelta(days=30))
    kept = ErrorRollup.objects.create(
        bucket=old, integration_id=provider_lotek_panthera.id, origin="disp",
        value="observation_delivery_failed", log_level=40, count=4,
    )
    out = StringIO()

    call_command(
        "rebuild_stats_rollups", "--from", old.isoformat(), "--to", (old + HOUR).isoformat(), stdout=out
    )

    assert ErrorRollup.objects.filter(pk=kept.pk, count=4).exists()
    assert "Errors not aggregated" in out.getvalue() and "1 bucket(s)" in out.getvalue()


@pytest.mark.parametrize("args", [
    ("--from", "not-a-date", "--to", "2026-11-20T16:00:00Z"),
    ("--from", "2026-11-20T16:00:00Z", "--to", "2026-11-20T14:00:00Z"),
])
def test_rebuild_command_rejects_a_bad_range(args):
    with pytest.raises(CommandError):
        call_command("rebuild_stats_rollups", *args)


def test_schedule_migration_uses_utc_crontabs_and_tolerates_same_fields_in_other_timezones():
    from django.apps import apps as django_apps
    from django_celery_beat.models import CrontabSchedule

    migration = importlib.import_module("stats.migrations.0002_rollup_schedule")
    PeriodicTask.objects.filter(task__in=[FREQUENT_TASK, DAILY_TASK]).delete()
    # Integration schedules store one crontab row per timezone.
    for timezone_name in ("America/Bogota", "Africa/Nairobi"):
        for minute, hour in (("*/10", "*"), ("30", "3")):
            CrontabSchedule.objects.create(minute=minute, hour=hour, timezone=timezone_name)

    migration.create_rollup_schedule(django_apps, None)

    for task in (FREQUENT_TASK, DAILY_TASK):
        assert str(PeriodicTask.objects.get(task=task).crontab.timezone) == "UTC"


def test_run_after_a_gap_longer_than_its_window_warns_about_the_uncovered_hours(caplog):
    state = RollupRunState.load()
    state.frequent_run_completed_at = datetime.datetime.now(UTC) - datetime.timedelta(days=3)
    state.save()

    with caplog.at_level("WARNING", logger="stats.services"):
        tasks.refresh_recent_stats_rollups.run()

    assert "rebuild_stats_rollups" in caplog.text


def test_run_inside_its_window_does_not_warn(caplog):
    tasks.refresh_recent_stats_rollups.run()

    with caplog.at_level("WARNING", logger="stats.services"):
        tasks.refresh_recent_stats_rollups.run()

    assert "rebuild_stats_rollups" not in caplog.text
