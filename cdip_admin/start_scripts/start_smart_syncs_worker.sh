#!/bin/sh

. $(dirname "$0")/django_common_startup.sh

WORKERS=2

celery -A cdip_admin worker -l info -c $WORKERS -Q smartsyncs -n smartsyncs@%h --time-limit=3660 --soft-time-limit=3600 2>&1
