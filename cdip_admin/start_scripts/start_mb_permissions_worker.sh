#!/bin/sh

. $(dirname "$0")/django_common_startup.sh

WORKERS=5

celery -A cdip_admin worker -l info -c $WORKERS -Q mb_permissions -n mb_permissions@%h 2>&1
