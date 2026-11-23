# Background Workers

We use Celery to run background tasks including Celery Beat as a scheduler. We also use Redis as Celery's broker backend.

## Running Celery Worker

You can run a basic celery worker with the following.

```bash
export DJANGO_SETTINGS_MODULE=cdip_admin.local_settings

celery -A cdip_admin worker -l DEBUG -P gevent -c 4
```

## Running Celery Beat

Celery Beat is the scheduler, driven by django-celery-beat and its database scheduler.
Schedules can be managed though the django admin.

```bash
export DJANGO_SETTINGS_MODULE=cdip_admin.local_settings

celery -A cdip_admin beat -l DEBUG --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## Stats Rollups

The `stats` app keeps hourly counts of throughput and errors for the `/v2/stats/` endpoints.
Two periodic tasks fill them. Both run on the `healthchecks` queue.

| Periodic task | Schedule | What it does |
|---|---|---|
| Refresh recent stats rollups (`stats.tasks.refresh_recent_stats_rollups`) | every 10 minutes | Recomputes the current and previous hour. |
| Reconcile stats rollups (`stats.tasks.reconcile_stats_rollups`) | daily at 03:30 UTC | Recomputes the last 48 hours, to pick up late deliveries. |

Both tasks are created **disabled**.

**To enable them:**

1. Set `STATS_THROUGHPUT_START` to an ISO 8601 time after every event consumer runs the release that added `GundiTrace.is_destination_copy`. Throughput is not aggregated for hours that start before it, or at all while it is unset.
2. Run `EXPLAIN` on the aggregation queries for a one-hour window on the production database and confirm index range scans on `created_at`, `delivered_at` and `discarded_at` of `integrations_gunditrace`, and on `created_at` of the activity log.
3. In Django admin, under Periodic tasks, enable "Refresh recent stats rollups". Watch database CPU for a day, then enable "Reconcile stats rollups".

**To stop the job** without a deploy, disable both periodic tasks in Django admin. The endpoints keep serving the rollups already stored, and report the time of the last successful run of each task.

Each hour is aggregated under a statement timeout (`STATS_ROLLUP_STATEMENT_TIMEOUT_MS`, 30 seconds by default). A run that hits it fails and does not advance its last-successful time.

**To re-aggregate a range by hand**, for example after the dispatcher events consumer fell more than 48 hours behind:

```bash
python3 manage.py rebuild_stats_rollups --from 2026-11-20T00:00:00Z --to 2026-11-21T00:00:00Z
```

The command leaves error counts untouched for hours older than `STATS_ERROR_SOURCE_RETENTION_DAYS` (20 days by default), because the activity log no longer holds them, and reports the hours it skipped.
