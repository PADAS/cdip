#!/bin/sh

. $(dirname "$0")/django_common_startup.sh

python3 $(dirname "$0")/dispatcher_events_consumer.py
