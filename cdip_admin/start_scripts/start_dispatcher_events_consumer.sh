#!/bin/sh

. $(dirname "$0")/django_common_startup.sh

python3 event_consumers/dispatcher_events_consumer.py
