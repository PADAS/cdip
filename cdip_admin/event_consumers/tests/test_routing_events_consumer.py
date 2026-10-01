import pytest
import json

from activity_log.models import ActivityLog
from event_consumers.routing_events_consumer import process_event
from integrations.models import GundiTrace


pytestmark = pytest.mark.django_db


def _message(mocker, event_dict):
    message = mocker.MagicMock()
    message.data = json.dumps(event_dict).encode("utf-8")
    return message


def test_process_observation_filtered_event(
        lotek_observation_trace, lotek_observation_filtered_event
):
    process_event(lotek_observation_filtered_event)

    event = json.loads(lotek_observation_filtered_event.data)
    event_data = event["payload"]
    lotek_observation_trace.refresh_from_db()
    assert str(lotek_observation_trace.destination.id) == str(event_data["destination_id"])
    assert str(lotek_observation_trace.discarded_at) == event["timestamp"]
    assert lotek_observation_trace.discard_reason == event_data["filtered_by"]
    # Filtering is not a delivery and not an error
    assert lotek_observation_trace.delivered_at is None
    assert lotek_observation_trace.has_error is False
    assert lotek_observation_filtered_event.ack.called

    event_data["source_external_id"] = lotek_observation_trace.source.external_id
    activity_log = ActivityLog.objects.filter(
        integration_id=event_data["data_provider_id"]
    ).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.INFO
    assert activity_log.origin == ActivityLog.Origin.TRANSFORMER
    assert activity_log.value == "observation_filtered"
    assert activity_log.details == event_data
    assert activity_log.is_reversible is False


def test_process_observation_filtered_event_with_second_destination(
        lotek_observation_trace,
        lotek_observation_filtered_event,
        lotek_observation_filtered_event_second_destination,
):
    process_event(lotek_observation_filtered_event)
    process_event(lotek_observation_filtered_event_second_destination)

    traces = GundiTrace.objects.filter(object_id=lotek_observation_trace.object_id)
    assert traces.count() == 2
    second_destination_id = json.loads(
        lotek_observation_filtered_event_second_destination.data
    )["payload"]["destination_id"]
    new_trace = traces.exclude(id=lotek_observation_trace.id).first()
    assert str(new_trace.destination.id) == str(second_destination_id)
    assert new_trace.data_provider == lotek_observation_trace.data_provider
    assert new_trace.source == lotek_observation_trace.source
    assert new_trace.discarded_at is not None
    assert new_trace.discard_reason == "device_whitelist"
    assert ActivityLog.objects.filter(value="observation_filtered").count() == 2


def test_process_observation_filtered_event_is_idempotent(
        lotek_observation_trace, lotek_observation_filtered_event
):
    # PubSub is at-least-once: a redelivered event must not add trace rows
    process_event(lotek_observation_filtered_event)
    process_event(lotek_observation_filtered_event)

    traces = GundiTrace.objects.filter(object_id=lotek_observation_trace.object_id)
    assert traces.count() == 1


def test_filtered_event_for_unknown_observation_is_ignored(
        mocker, lotek_observation_trace, integrations_list_er
):
    event = _message(mocker, {
        "event_id": "c5d2f9b3-1e4c-4d7b-8f83-8c4a5c9e2f33",
        "timestamp": "2026-09-30 18:11:00.000000+00:00",
        "schema_version": "v1",
        "event_type": "ObservationFiltered",
        "payload": {
            "gundi_id": "11111111-2222-3333-4444-555555555555",
            "data_provider_id": str(lotek_observation_trace.data_provider.id),
            "destination_id": str(integrations_list_er[0].id),
        },
    })
    process_event(event)

    assert event.ack.called
    assert not ActivityLog.objects.filter(value="observation_filtered").exists()


def test_unknown_event_type_is_discarded(mocker):
    event = _message(mocker, {
        "schema_version": "v1",
        "event_type": "SomethingElse",
        "payload": {},
    })
    process_event(event)

    assert event.ack.called
    assert not event.nack.called


def test_unsupported_schema_version_is_discarded(
        mocker, lotek_observation_trace, integrations_list_er
):
    event_dict = json.loads(
        json.dumps({
            "schema_version": "v2",
            "event_type": "ObservationFiltered",
            "payload": {
                "gundi_id": str(lotek_observation_trace.object_id),
                "data_provider_id": str(lotek_observation_trace.data_provider.id),
                "destination_id": str(integrations_list_er[0].id),
            },
        })
    )
    event = _message(mocker, event_dict)
    process_event(event)

    assert event.ack.called
    lotek_observation_trace.refresh_from_db()
    assert lotek_observation_trace.destination is None
    assert not ActivityLog.objects.filter(value="observation_filtered").exists()


def test_invalid_json_is_discarded(mocker):
    message = mocker.MagicMock()
    message.data = b"not json"
    process_event(message)

    assert message.ack.called
    assert not message.nack.called
