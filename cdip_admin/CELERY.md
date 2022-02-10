# Background Workers

We use Celery to run background tasks including Celery Beat as a scheduler. We also use Redis as Celery's broker backend.

## Running Celery Worker

You can run a basic celery worker with the following.

```bash
export DJANGO_SETTINGS_MODULE=cdip_admin.local_settings

celery -A cdip_admin worker -l DEBUG -P gevent -c 4
```

## Running Celery Beat

Celery Beat is the scheduler, driven by the `app.conf.beat_schedule` within cdip_admin/celery.py.

```bash
export DJANGO_SETTINGS_MODULE=cdip_admin.local_settings

celery -A cdip_admin beat -l DEBUG
```
