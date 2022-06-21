#!/bin/sh

. $(dirname "$0")/django_common_startup.sh

WORKERS=5

celery -A cdip_admin worker -Q default -l info -c $WORKERS -P gevent -n default 2>&1