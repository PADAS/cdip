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
    # Check that error details have been recorded
    event_error_details = json.loads(pull_observations_action_failed_event.data)["payload"]
    log_details = activity_log.details
    assert log_details == event_error_details


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


# --- GUNDI-5550: resilience to DB connection loss ---

from django.db import InterfaceError, OperationalError


@pytest.mark.parametrize("db_error", [
    InterfaceError("connection already closed"),
    OperationalError("server closed the connection unexpectedly"),
])
def test_transient_db_error_nacks_message_for_redelivery(
        mocker, db_error, provider_lotek_panthera, pull_observations_action_started_event
):
    # A dead DB connection must trigger redelivery, not a silent drop (GUNDI-5549)
    mocker.patch.dict(
        "event_consumers.integration_events_consumer.event_handlers",
        {"IntegrationActionStarted": mocker.MagicMock(side_effect=db_error)},
    )
    process_event(pull_observations_action_started_event)
    pull_observations_action_started_event.nack.assert_called_once()
    pull_observations_action_started_event.ack.assert_not_called()


def test_transient_db_error_resets_connections(
        mocker, provider_lotek_panthera, pull_observations_action_started_event
):
    mocked_refresh = mocker.patch(
        "event_consumers.integration_events_consumer.refresh_db_connections"
    )
    mocker.patch.dict(
        "event_consumers.integration_events_consumer.event_handlers",
        {"IntegrationActionStarted": mocker.MagicMock(side_effect=InterfaceError("connection already closed"))},
    )
    process_event(pull_observations_action_started_event)
    # Once on entry (routine refresh) + once after the failure (drop the dead connection)
    assert mocked_refresh.call_count == 2


def test_unexpected_error_still_acks_message(
        mocker, provider_lotek_panthera, pull_observations_action_started_event
):
    # Non-DB errors keep the current log-and-ack behavior: without a
    # dead-letter topic, nacking them would loop a poison message forever.
    mocker.patch.dict(
        "event_consumers.integration_events_consumer.event_handlers",
        {"IntegrationActionStarted": mocker.MagicMock(side_effect=ValueError("boom"))},
    )
    process_event(pull_observations_action_started_event)
    pull_observations_action_started_event.ack.assert_called_once()
    pull_observations_action_started_event.nack.assert_not_called()


def test_successful_processing_acks_message_exactly_once(
        mocker, provider_lotek_panthera, pull_observations_action_started_event
):
    mocked_refresh = mocker.patch(
        "event_consumers.integration_events_consumer.refresh_db_connections"
    )
    process_event(pull_observations_action_started_event)
    pull_observations_action_started_event.ack.assert_called_once()
    pull_observations_action_started_event.nack.assert_not_called()
    mocked_refresh.assert_called_once()  # routine per-message refresh


def test_invalid_json_message_is_discarded_without_raising(mocker):
    message = mocker.MagicMock()
    message.data = b"not json {"
    process_event(message)  # must not raise
    message.ack.assert_called_once()
    message.nack.assert_not_called()
