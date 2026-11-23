from django.db import migrations

FREQUENT_TASK = "stats.tasks.refresh_recent_stats_rollups"
DAILY_TASK = "stats.tasks.reconcile_stats_rollups"


def create_rollup_schedule(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    every_ten_minutes, _ = CrontabSchedule.objects.get_or_create(
        minute="*/10", hour="*", day_of_week="*", day_of_month="*", month_of_year="*",
    )
    daily, _ = CrontabSchedule.objects.get_or_create(
        minute="30", hour="3", day_of_week="*", day_of_month="*", month_of_year="*",
    )
    # Both tasks are created disabled. An operator enables them in Django admin
    # after checking the query cost in production, and disables them to stop
    # the job without a deploy.
    PeriodicTask.objects.get_or_create(
        task=FREQUENT_TASK,
        defaults={"crontab": every_ten_minutes, "name": "Refresh recent stats rollups", "enabled": False},
    )
    PeriodicTask.objects.get_or_create(
        task=DAILY_TASK,
        defaults={"crontab": daily, "name": "Reconcile stats rollups", "enabled": False},
    )


def delete_rollup_schedule(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(task__in=[FREQUENT_TASK, DAILY_TASK]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("stats", "0001_initial"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.RunPython(create_rollup_schedule, delete_rollup_schedule),
    ]
