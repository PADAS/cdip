#!/bin/sh

. $(dirname "$0")/django_common_startup.sh

WORKERS=2

celery -A cdip_admin worker -l info -c $WORKERS -Q systemevents -n systemevents@%h 2>&1
