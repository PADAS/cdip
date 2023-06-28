#!/bin/sh

. $(dirname "$0")/django_common_startup.sh

celery -A cdip_admin beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
