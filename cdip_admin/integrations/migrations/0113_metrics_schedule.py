from django.db import migrations


def create_healthcheck_schedule(apps, schema_editor):
    CrontabSchedule = apps.get_model('django_celery_beat', 'CrontabSchedule')
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')

    # Get or create periodic task to run once a day at midnight
    schedule, created = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="0",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
    )
    PeriodicTask.objects.get_or_create(
        task="integrations.tasks.calculate_integration_metrics_in_batches",
        defaults={
            "crontab": schedule,
            "name": "Calculate Integration Metrics",
        }
    )


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0112_integrationmetrics'),
    ]

    operations = [
        migrations.RunPython(create_healthcheck_schedule, reverse_code=migrations.RunPython.noop),
    ]
