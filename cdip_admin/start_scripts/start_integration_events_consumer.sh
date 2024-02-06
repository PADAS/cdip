#!/bin/sh
. $(dirname "$0")/django_common_startup.sh
export PYTHONPATH=$PYTHONPATH:`pwd`
python3 event_consumers/integration_events_consumer.py
