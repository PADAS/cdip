import pytest
import json

from activity_log.models import ActivityLog
from event_consumers.dispatcher_events_consumer import process_event, data_type_str_map, \
    build_delivery_failed_event_v2_from_v1_data, build_update_failed_event_v2_from_v1_data
from integrations.models import GundiTrace


pytestmark = pytest.mark.django_db


def test_process_observation_delivered_event_with_er_destination(
        trap_tagger_event_trace, trap_tagger_to_er_observation_delivered_event
):
    # Test the case when an observation is delivered to a single destination successfully
    process_event(trap_tagger_to_er_observation_delivered_event)
    event_data = json.loads(trap_tagger_to_er_observation_delivered_event.data)["payload"]
    event_data["source_external_id"] = trap_tagger_event_trace.source.external_id
    trap_tagger_event_trace.refresh_from_db()
    assert str(trap_tagger_event_trace.destination.id) == str(event_data["destination_id"])
    assert str(trap_tagger_event_trace.external_id) == str(event_data["external_id"])
    assert str(trap_tagger_event_trace.delivered_at) == str(event_data["delivered_at"])
    # Check that the event was recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=event_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.DEBUG
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_delivery_succeeded"
    assert activity_log.title == f"Event {trap_tagger_event_trace.object_id} Delivered to '{trap_tagger_event_trace.destination.base_url}'"
    assert activity_log.details == event_data


def test_process_observation_delivered_event_with_smart_destination(
        trap_tagger_event_trace, trap_tagger_to_smart_observation_delivered_event
):
    # Test the case when an observation is delivered to a single destination successfully
    process_event(trap_tagger_to_smart_observation_delivered_event)
    event_data = json.loads(trap_tagger_to_smart_observation_delivered_event.data)["payload"]
    event_data["source_external_id"] = trap_tagger_event_trace.source.external_id
    trap_tagger_event_trace.refresh_from_db()
    assert str(trap_tagger_event_trace.destination.id) == str(event_data["destination_id"])
    assert str(trap_tagger_event_trace.external_id) == str(event_data["external_id"])
    assert str(trap_tagger_event_trace.delivered_at) == str(event_data["delivered_at"])
    # Check that the event was recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=event_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.DEBUG
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_delivery_succeeded"
    assert activity_log.title == f"Event {trap_tagger_event_trace.object_id} Delivered to '{trap_tagger_event_trace.destination.base_url}'"
    assert activity_log.details == event_data


def test_process_observation_delivered_event_with_two_er_destinations(
        trap_tagger_event_trace, trap_tagger_to_er_observation_delivered_event, trap_tagger_observation_delivered_event_two
):
    # Test the case when an observation is delivered to two destinations successfully
    process_event(trap_tagger_to_er_observation_delivered_event)  # One event for one destination
    # Check that we have two traces in the database now (for the second destination)
    event_data = json.loads(trap_tagger_to_er_observation_delivered_event.data)["payload"]
    assert GundiTrace.objects.filter(object_id=event_data["gundi_id"]).count() == 1

    # Check that the data related to the first destination was saved in the database
    trace_one = GundiTrace.objects.get(
        object_id=event_data["gundi_id"],
        destination__id=event_data["destination_id"]
    )
    event_data["source_external_id"] = trace_one.source.external_id
    assert str(trace_one.external_id) == str(event_data["external_id"])
    # Check that the event was recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=event_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.DEBUG
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_delivery_succeeded"
    assert activity_log.title == f"Event {trace_one.object_id} Delivered to '{trace_one.destination.base_url}'"
    assert activity_log.details == event_data

    process_event(trap_tagger_observation_delivered_event_two)  # A second event for the other destination
    assert GundiTrace.objects.filter(object_id=event_data["gundi_id"]).count() == 2
    # Check that the data related to the second destination was saved in the database
    event_data = json.loads(trap_tagger_observation_delivered_event_two.data)["payload"]
    trace_two = GundiTrace.objects.get(
        object_id=event_data["gundi_id"],
        destination__id=event_data["destination_id"]
    )
    event_data["source_external_id"] = trace_two.source.external_id
    assert str(trace_two.external_id) == str(event_data["external_id"])
    # Check that the event was recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=event_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.DEBUG
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_delivery_succeeded"
    assert activity_log.title == f"Event {trace_two.object_id} Delivered to '{trace_two.destination.base_url}'"
    assert activity_log.details == event_data


def test_process_observation_delivered_event_with_er_and_smart_destinations(
        trap_tagger_event_trace, trap_tagger_to_er_observation_delivered_event, trap_tagger_to_smart_observation_delivered_event
):
    # Test the case when an observation is delivered to two destinations successfully
    process_event(trap_tagger_to_er_observation_delivered_event)  # One event for one destination
    # Check that we have two traces in the database now (for the second destination)
    event_data = json.loads(trap_tagger_to_er_observation_delivered_event.data)["payload"]
    assert GundiTrace.objects.filter(object_id=event_data["gundi_id"]).count() == 1

    # Check that the data related to the first destination was saved in the database
    trace_one = GundiTrace.objects.get(
        object_id=event_data["gundi_id"],
        destination__id=event_data["destination_id"]
    )
    event_data["source_external_id"] = trace_one.source.external_id
    assert str(trace_one.external_id) == str(event_data["external_id"])
    # Check that the event was recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=event_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.DEBUG
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_delivery_succeeded"
    assert activity_log.title == f"Event {trace_one.object_id} Delivered to '{trace_one.destination.base_url}'"
    assert activity_log.details == event_data

    process_event(trap_tagger_to_smart_observation_delivered_event)  # A second event for the other destination
    assert GundiTrace.objects.filter(object_id=event_data["gundi_id"]).count() == 2
    # Check that the data related to the second destination was saved in the database
    event_data = json.loads(trap_tagger_to_smart_observation_delivered_event.data)["payload"]
    trace_two = GundiTrace.objects.get(
        object_id=event_data["gundi_id"],
        destination__id=event_data["destination_id"]
    )
    event_data["source_external_id"] = trace_two.source.external_id
    assert str(trace_two.external_id) == str(event_data["external_id"])
    # Check that the event was recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=event_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.DEBUG
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_delivery_succeeded"
    assert activity_log.title == f"Event {trace_two.object_id} Delivered to '{trace_two.destination.base_url}'"
    assert activity_log.details == event_data

@pytest.mark.parametrize(
    "observation_delivery_failed_event",
    ["schema_v1", "schema_v2"],
    indirect=["observation_delivery_failed_event"])
def test_process_observation_delivery_failed_event(
        request, trap_tagger_event_trace, observation_delivery_failed_event
):
    # Test the case when an observation fails to get delivered and we receive the event notification
    process_event(observation_delivery_failed_event)
    trap_tagger_event_trace.refresh_from_db()
    event_dict = json.loads(observation_delivery_failed_event.data)
    schema_version = event_dict.get("schema_version")
    observation_data = event_dict["payload"] if schema_version == "v1" else event_dict["payload"]["observation"]
    observation_data["source_external_id"] = trap_tagger_event_trace.source.external_id

    # Check that the error is recorded
    assert trap_tagger_event_trace.has_error
    assert trap_tagger_event_trace.error == "Delivery Failed at the Dispatcher."
    # Other fields must not be updated as the delivery has failed
    assert trap_tagger_event_trace.destination
    assert not trap_tagger_event_trace.external_id
    assert not trap_tagger_event_trace.delivered_at
    # Check that the event was recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=observation_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.ERROR
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_delivery_failed"
    assert activity_log.title == f"Error Delivering Event {trap_tagger_event_trace.object_id} to '{trap_tagger_event_trace.destination.base_url}'"
    log_details = activity_log.details
    if schema_version == "v1":
        assert log_details.get("error") == "Delivery Failed at the Dispatcher. Please update this dispatcher to see more details here."
        v2_event = build_delivery_failed_event_v2_from_v1_data(event_dict)
        expected_data = json.loads(json.dumps(v2_event.payload.dict(), default=str))
        assert log_details.get("observation") == expected_data.get("observation")
    else:
        event_payload = event_dict["payload"]
        assert log_details.get("error") == event_payload.get("error")
        assert log_details.get("server_response_status") == event_payload.get("server_response_status")
        assert log_details.get("server_response_body") == event_payload.get("server_response_body")
    assert activity_log.details.get("source_external_id") == observation_data["source_external_id"]



def test_process_observation_delivered_event_without_external_id(
        trap_tagger_to_movebank_observation_trace, trap_tagger_to_movebank_observation_delivered_event
):
    # Test the case when an observation is delivered to a single destination successfully
    # But no external id is returned. (for example, Movebank)
    process_event(trap_tagger_to_movebank_observation_delivered_event)
    event_data = json.loads(trap_tagger_to_movebank_observation_delivered_event.data)["payload"]
    trap_tagger_to_movebank_observation_trace.refresh_from_db()
    assert str(trap_tagger_to_movebank_observation_trace.destination.id) == str(event_data["destination_id"])
    assert not trap_tagger_to_movebank_observation_trace.external_id  # Movebank API doesn't return an ID
    assert str(trap_tagger_to_movebank_observation_trace.delivered_at) == str(event_data["delivered_at"])


@pytest.mark.parametrize(
    "observation_delivery_failed_event",
    ["schema_v1", "schema_v2"],
    indirect=["observation_delivery_failed_event"])
def test_process_observation_delivered_event_after_retry_with_single_destination(
        trap_tagger_event_trace, observation_delivery_failed_event,
        trap_tagger_to_er_observation_delivered_event
):
    # Test the case when an observation fails to get delivered the first time
    # and succeeds on a second try.
    process_event(observation_delivery_failed_event)
    trap_tagger_event_trace.refresh_from_db()
    assert trap_tagger_event_trace.has_error
    assert trap_tagger_event_trace.error == "Delivery Failed at the Dispatcher."
    # Check that the event was recorded in the activity log
    event_dict = json.loads(observation_delivery_failed_event.data)
    schema_version = event_dict.get("schema_version")
    observation_data = event_dict["payload"] if schema_version == "v1" else event_dict["payload"]["observation"]
    observation_data["source_external_id"] = trap_tagger_event_trace.source.external_id

    activity_log = ActivityLog.objects.filter(integration_id=observation_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.ERROR
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_delivery_failed"
    assert activity_log.title == f"Error Delivering Event {trap_tagger_event_trace.object_id} to '{trap_tagger_event_trace.destination.base_url}'"
    log_details = activity_log.details
    if schema_version == "v1":
        assert log_details.get("error") == "Delivery Failed at the Dispatcher. Please update this dispatcher to see more details here."
        v2_event = build_delivery_failed_event_v2_from_v1_data(event_dict)
        expected_data = json.loads(json.dumps(v2_event.payload.dict(), default=str))
        assert log_details.get("observation") == expected_data.get("observation")
    else:
        event_payload = event_dict["payload"]
        assert log_details.get("error") == event_payload.get("error")
        assert log_details.get("server_response_status") == event_payload.get("server_response_status")
        assert log_details.get("server_response_body") == event_payload.get("server_response_body")
    assert activity_log.details.get("source_external_id") == observation_data["source_external_id"]

    # Process the second event. The observation was delivered with success now
    process_event(trap_tagger_to_er_observation_delivered_event)
    observation_data = json.loads(trap_tagger_to_er_observation_delivered_event.data)["payload"]
    trap_tagger_event_trace.refresh_from_db()
    observation_data["source_external_id"] = trap_tagger_event_trace.source.external_id
    assert not trap_tagger_event_trace.has_error
    assert not trap_tagger_event_trace.error
    assert str(trap_tagger_event_trace.destination.id) == str(observation_data["destination_id"])
    assert str(trap_tagger_event_trace.external_id) == str(observation_data["external_id"])
    assert str(trap_tagger_event_trace.delivered_at) == str(observation_data["delivered_at"])
    # Check that the event was recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=observation_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.DEBUG
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_delivery_succeeded"
    assert activity_log.title == f"Event {trap_tagger_event_trace.object_id} Delivered to '{trap_tagger_event_trace.destination.base_url}'"
    assert activity_log.details == observation_data


def test_process_observation_delivered_event_after_retry_with_two_destinations(
        trap_tagger_event_trace,
        trap_tagger_observation_delivery_failed_schema_v1_event_one,
        trap_tagger_observation_delivery_failed_schema_v1_event_two,
        trap_tagger_to_er_observation_delivered_event,
        trap_tagger_observation_delivered_event_two
):
    # Test the case when an observation fails to get delivered the first time to two destinations
    # and succeeds on a second try for both destinations
    process_event(trap_tagger_observation_delivery_failed_schema_v1_event_one)
    trap_tagger_event_trace.refresh_from_db()
    assert trap_tagger_event_trace.has_error
    assert trap_tagger_event_trace.error == "Delivery Failed at the Dispatcher."
    process_event(trap_tagger_observation_delivery_failed_schema_v1_event_two)
    event_2_data = json.loads(trap_tagger_observation_delivered_event_two.data)["payload"]
    trap_tagger_event_trace_2 = GundiTrace.objects.get(
        object_id=trap_tagger_event_trace.object_id,
        destination__id=str(event_2_data["destination_id"])
    )
    assert trap_tagger_event_trace_2.has_error
    assert trap_tagger_event_trace_2.error == "Delivery Failed at the Dispatcher."

    process_event(trap_tagger_to_er_observation_delivered_event)
    event_data = json.loads(trap_tagger_to_er_observation_delivered_event.data)["payload"]
    trap_tagger_event_trace.refresh_from_db()
    assert not trap_tagger_event_trace.has_error
    assert not trap_tagger_event_trace.error
    assert str(trap_tagger_event_trace.destination.id) == str(event_data["destination_id"])
    assert str(trap_tagger_event_trace.external_id) == str(event_data["external_id"])
    assert str(trap_tagger_event_trace.delivered_at) == str(event_data["delivered_at"])

    process_event(trap_tagger_observation_delivered_event_two)
    event_data = json.loads(trap_tagger_observation_delivered_event_two.data)["payload"]
    trap_tagger_event_trace_2.refresh_from_db()
    assert not trap_tagger_event_trace_2.has_error
    assert not trap_tagger_event_trace_2.error
    assert str(trap_tagger_event_trace_2.destination.id) == str(event_data["destination_id"])
    assert str(trap_tagger_event_trace_2.external_id) == str(event_data["external_id"])
    assert str(trap_tagger_event_trace_2.delivered_at) == str(event_data["delivered_at"])


def test_process_observation_updated_event(
        trap_tagger_event_update_trace, trap_tagger_observation_updated_event
):
    # Test the case when an observation is updated in a destination successfully
    process_event(trap_tagger_observation_updated_event)
    event_data = json.loads(trap_tagger_observation_updated_event.data)["payload"]
    event_data["source_external_id"] = trap_tagger_event_update_trace.source.external_id
    trap_tagger_event_update_trace.refresh_from_db()
    assert str(trap_tagger_event_update_trace.last_update_delivered_at) == str(event_data["updated_at"])
    # Check that the event was recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=event_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.DEBUG
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_update_succeeded"
    assert activity_log.title == f"Event {trap_tagger_event_update_trace.object_id} updated in '{trap_tagger_event_update_trace.destination.base_url}'"
    assert activity_log.details == event_data


@pytest.mark.parametrize(
    "observation_update_failed_event",
    ["schema_v1", "schema_v2"],
    indirect=["observation_update_failed_event"])
def test_process_observation_update_failed_event(
        trap_tagger_event_update_trace, observation_update_failed_event
):
    # Test the case when an observation is updated in a destination successfully
    process_event(observation_update_failed_event)
    event_dict = json.loads(observation_update_failed_event.data)
    schema_version = event_dict.get("schema_version")
    observation_data = event_dict["payload"] if schema_version == "v1" else event_dict["payload"]["observation"]
    observation_data["source_external_id"] = trap_tagger_event_update_trace.source.external_id

    trap_tagger_event_update_trace.refresh_from_db()
    assert trap_tagger_event_update_trace.last_update_delivered_at is None
    assert trap_tagger_event_update_trace.has_error
    assert trap_tagger_event_update_trace.error == "Update Failed at the Dispatcher."
    # Check that the error was recorded in the activity logs
    activity_log = ActivityLog.objects.filter(integration_id=observation_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.ERROR
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_update_failed"
    assert activity_log.title == f"Error Updating Event {trap_tagger_event_update_trace.object_id} in '{trap_tagger_event_update_trace.destination.base_url}'"
    log_details = activity_log.details
    if schema_version == "v1":
        assert log_details.get("error") == "Update Failed at the Dispatcher. Please update this dispatcher to see more details here."
        v2_event = build_update_failed_event_v2_from_v1_data(event_dict)
        expected_data = json.loads(json.dumps(v2_event.payload.dict(), default=str))
        assert log_details.get("observation") == expected_data.get("observation")
    else:
        event_payload = event_dict["payload"]
        assert log_details.get("error") == event_payload.get("error")
        assert log_details.get("server_response_status") == event_payload.get("server_response_status")
        assert log_details.get("server_response_body") == event_payload.get("server_response_body")
    assert activity_log.details.get("source_external_id") == observation_data["source_external_id"]


def test_process_dispatcher_log_event(
        trap_tagger_event_trace, wpswatch_dispatcher_log_event
):
    # Test the case when a dispatcher logs a message
    process_event(wpswatch_dispatcher_log_event)
    event_data = json.loads(wpswatch_dispatcher_log_event.data)["payload"]
    # Check that the event was recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=event_data["destination_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == event_data["level"]
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "custom_dispatcher_log"
    assert activity_log.title == event_data['title']
    assert not activity_log.is_reversible


@pytest.mark.parametrize("trace,delivery_event,stream_type", [
    ("trap_tagger_event_trace", "trap_tagger_to_er_observation_delivered_event", "Event"),
    ("attachment_delivered_trace", "trap_tagger_to_er_attachment_delivered_event", "Attachment"),
    ("trap_tagger_to_movebank_observation_trace", "trap_tagger_to_movebank_observation_delivered_event", "Observation"),
])
def test_show_stream_type_in_activity_log_title_on_observation_delivery(
        request, trace, delivery_event, stream_type
):
    trace = request.getfixturevalue(trace)
    delivery_event = request.getfixturevalue(delivery_event)
    process_event(delivery_event)
    trace.refresh_from_db()
    event_data = json.loads(delivery_event.data)["payload"]
    # Check that the event was recorded with hte right title in the activity logs
    activity_log = ActivityLog.objects.filter(integration_id=event_data["data_provider_id"]).first()
    assert activity_log.title == f"{stream_type} {trace.object_id} Delivered to '{trace.destination.base_url}'"
