#!/bin/sh

. $(dirname "$0")/django_common_startup.sh

celery -A cdip_admin beat -l info 
