from __future__ import absolute_import

import os
from datetime import timedelta

from django.conf import settings
from kombu import Exchange, Queue

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cdip_admin.settings")
app = Celery("cdip_admin")
# Using a string here means the worker will not have to
# pickle the object when using Windows.

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(
    lambda: settings.INSTALLED_APPS
    + [
        "cdip_admin",
    ]
)

default_exchange = Exchange(app.conf.task_default_exchange)
app.autodiscover_tasks()

# Celery 4 changed from UPPERCASE to lower with new names. we've updated them here, but not yet in settings.py
# We want input from chis d et al.
# read more here: http://docs.celeryproject.org/en/latest/userguide/configuration.html?highlight=CELERY_DEFAULT_QUEUE#std:setting-beat_schedule
# Defining queues
app.conf.task_queues = (
    Queue(
        app.conf.task_default_queue,
        default_exchange,
        routing_key=app.conf.task_default_routing_key,
    ),
    # Queue('maintenance', default_exchange, routing_key='maintenance.tasks'),
)


# app.conf.task_routes = {
# }

app.conf.beat_schedule = {
    # Run pulse routine frequently and on a high-priority queue.
    "beat-pulse": {
        "task": "cdip_admin.tasks.celerybeat_pulse",
        "schedule": timedelta(seconds=60),
    },
    # Run sync integrations
    "run-sync-integrations": {
        "task": "sync_integrations.tasks.run_sync_integrations",
        "schedule": timedelta(
            minutes=settings.CELERY_TASK_SYNC_INTEGRATION_INTERVAL_MINUTES
        ),
    },
}

# Patch Celery's configuration with some attributes that Celery_once will
# use to control task creation.

app.conf.ONCE = {
    "backend": "celery_once.backends.Redis",
    "settings": {
        # Co-opt the URL for Celery to use for storing celery_once semaphores.
        "url": settings.CELERY_BROKER_URL,
        # three minutes, default expiration for a celery_once semaphore.
        "default_timeout": 60 * 3,
    },
}


@app.task(bind=True)
def debug_task(self):
    print("Debug task")


@setup_logging.connect
def cdip_server_logging(loglevel, **kwargs):
    from cdip_admin.logconfiguration import init as init_logging

    init_logging()
