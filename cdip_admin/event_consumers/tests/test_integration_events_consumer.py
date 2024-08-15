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


def test_process_webhook_started_event(
    provider_liquidtech_with_webhook_config, webhook_started_event_pubsub
):
    process_event(webhook_started_event_pubsub)

    # Check that an activity logs is recorded
    activity_log = ActivityLog.objects.filter(
        log_type=ActivityLog.LogTypes.EVENT, integration=provider_liquidtech_with_webhook_config
    ).first()
    assert activity_log
    assert activity_log.log_level == ActivityLog.LogLevels.INFO
    assert activity_log.origin == ActivityLog.Origin.INTEGRATION
    assert activity_log.value == "integration_webhook_started"
    assert not activity_log.is_reversible
    event_dict = json.loads(webhook_started_event_pubsub.data)
    assert activity_log.details == event_dict.get("payload")


def test_process_webhook_complete_event(
    provider_liquidtech_with_webhook_config, webhook_complete_event_pubsub
):
    process_event(webhook_complete_event_pubsub)

    # Check that an activity logs is recorded
    activity_log = ActivityLog.objects.filter(
        log_type=ActivityLog.LogTypes.EVENT, integration=provider_liquidtech_with_webhook_config
    ).first()
    assert activity_log
    assert activity_log.log_level == ActivityLog.LogLevels.INFO
    assert activity_log.origin == ActivityLog.Origin.INTEGRATION
    assert activity_log.value == "integration_webhook_complete"
    assert not activity_log.is_reversible
    event_dict = json.loads(webhook_complete_event_pubsub.data)
    assert activity_log.details == event_dict.get("payload")


def test_process_webhook_failed_event(
    provider_liquidtech_with_webhook_config, webhook_failed_event_pubsub
):
    process_event(webhook_failed_event_pubsub)

    # Check that an activity logs is recorded
    activity_log = ActivityLog.objects.filter(
        log_type=ActivityLog.LogTypes.EVENT, integration=provider_liquidtech_with_webhook_config
    ).first()
    assert activity_log
    assert activity_log.log_level == ActivityLog.LogLevels.ERROR
    assert activity_log.origin == ActivityLog.Origin.INTEGRATION
    assert activity_log.value == "integration_webhook_failed"
    assert not activity_log.is_reversible
    event_dict = json.loads(webhook_failed_event_pubsub.data)
    assert activity_log.details == event_dict.get("payload")


def test_process_webhook_custom_activity_log_event(
    provider_liquidtech_with_webhook_config, webhook_custom_activity_log_event
):
    event_payload = json.loads(webhook_custom_activity_log_event.data)[
        "payload"
    ]
    process_event(webhook_custom_activity_log_event)

    # Check that an activity logs is recorded
    activity_log = ActivityLog.objects.filter(
        log_type=ActivityLog.LogTypes.EVENT, integration=provider_liquidtech_with_webhook_config
    ).first()
    assert activity_log
    assert activity_log.origin == ActivityLog.Origin.INTEGRATION
    assert activity_log.value == "integration_webhook_custom_log"
    assert activity_log.log_level == event_payload["level"]
    assert activity_log.title == event_payload["title"]
    assert activity_log.details == event_payload
    assert activity_log.is_reversible is False
