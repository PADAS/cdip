import pytest
import json
from activity_log.models import ActivityLog
from event_consumers.integration_events_consumer import process_event


pytestmark = pytest.mark.django_db


def test_process_action_started_event(
    provider_lotek_panthera, pull_observations_action_started_event
):
    process_event(pull_observations_action_started_event)

    # Check that an activity logs is recorded
    activity_log = ActivityLog.objects.filter(
        log_type=ActivityLog.LogTypes.EVENT, integration=provider_lotek_panthera
    ).first()
    assert activity_log
    assert activity_log.log_level == ActivityLog.LogLevels.INFO
    assert activity_log.origin == ActivityLog.Origin.INTEGRATION
    assert activity_log.value == "integration_action_started"
    assert activity_log.is_reversible is False


def test_process_action_complete_event(
    provider_lotek_panthera, pull_observations_action_complete_event
):
    process_event(pull_observations_action_complete_event)

    # Check that an activity logs is recorded
    activity_log = ActivityLog.objects.filter(
        log_type=ActivityLog.LogTypes.EVENT, integration=provider_lotek_panthera
    ).first()
    assert activity_log
    assert activity_log.log_level == ActivityLog.LogLevels.INFO
    assert activity_log.origin == ActivityLog.Origin.INTEGRATION
    assert activity_log.value == "integration_action_complete"
    assert activity_log.is_reversible is False


def test_process_action_failed_event(
    provider_lotek_panthera, pull_observations_action_failed_event
):
    process_event(pull_observations_action_failed_event)

    # Check that an activity logs is recorded
    activity_log = ActivityLog.objects.filter(
        log_type=ActivityLog.LogTypes.EVENT, integration=provider_lotek_panthera
    ).first()
    assert activity_log
    assert activity_log.log_level == ActivityLog.LogLevels.ERROR
    assert activity_log.origin == ActivityLog.Origin.INTEGRATION
    assert activity_log.value == "integration_action_failed"
    assert activity_log.is_reversible is False


def test_process_custom_activity_log_event(
    provider_lotek_panthera, pull_observations_action_custom_log_event
):
    event_payload = json.loads(pull_observations_action_custom_log_event.data)[
        "payload"
    ]
    process_event(pull_observations_action_custom_log_event)

    # Check that an activity logs is recorded
    activity_log = ActivityLog.objects.filter(
        log_type=ActivityLog.LogTypes.EVENT, integration=provider_lotek_panthera
    ).first()
    assert activity_log
    assert activity_log.origin == ActivityLog.Origin.INTEGRATION
    assert activity_log.value == "integration_custom_log"
    assert activity_log.log_level == event_payload["level"]
    assert activity_log.title == event_payload["title"]
    assert activity_log.details == event_payload
    assert activity_log.is_reversible is False
