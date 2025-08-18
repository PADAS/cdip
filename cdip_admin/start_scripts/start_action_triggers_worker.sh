#!/bin/sh

. $(dirname "$0")/django_common_startup.sh

WORKERS=2

celery -A cdip_admin worker -l info -c $WORKERS -Q actiontriggers -n actiontriggers@%h --time-limit=600 --soft-time-limit=300 2>&1
