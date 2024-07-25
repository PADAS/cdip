import pytest
import json

from activity_log.models import ActivityLog
from event_consumers.dispatcher_events_consumer import process_event
from integrations.models import GundiTrace


pytestmark = pytest.mark.django_db


def test_process_observation_delivered_event_with_single_destination(
        trap_tagger_event_trace, trap_tagger_observation_delivered_event
):
    # Test the case when an observation is delivered to a single destination successfully
    process_event(trap_tagger_observation_delivered_event)
    event_data = json.loads(trap_tagger_observation_delivered_event.data)["payload"]
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
    assert activity_log.title == f"Observation Delivered to '{trap_tagger_event_trace.destination.base_url}'"
    assert activity_log.details == event_data


def test_process_observation_delivered_event_with_two_destinations(
        trap_tagger_event_trace, trap_tagger_observation_delivered_event, trap_tagger_observation_delivered_event_two
):
    # Test the case when an observation is delivered to two destinations successfully
    process_event(trap_tagger_observation_delivered_event)  # One event for one destination
    # Check that we have two traces in the database now (for the second destination)
    event_data = json.loads(trap_tagger_observation_delivered_event.data)["payload"]
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
    assert activity_log.title == f"Observation Delivered to '{trace_one.destination.base_url}'"
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
    assert activity_log.title == f"Observation Delivered to '{trace_two.destination.base_url}'"
    assert activity_log.details == event_data


def test_process_observation_delivery_failed_event(
        trap_tagger_event_trace, trap_tagger_observation_delivery_failed_event
):
    # Test the case when an observation fails to get delivered and we receive the event notification
    process_event(trap_tagger_observation_delivery_failed_event)
    trap_tagger_event_trace.refresh_from_db()
    event_data = json.loads(trap_tagger_observation_delivery_failed_event.data)["payload"]
    event_data["source_external_id"] = trap_tagger_event_trace.source.external_id
    # Check that the error is recorded
    assert trap_tagger_event_trace.has_error
    assert trap_tagger_event_trace.error == "Delivery Failed at the Dispatcher."
    # Other fields must not be updated as the delivery has failed
    assert trap_tagger_event_trace.destination
    assert not trap_tagger_event_trace.external_id
    assert not trap_tagger_event_trace.delivered_at
    # Check that the event was recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=event_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.ERROR
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_delivery_failed"
    assert activity_log.title == f"Error Delivering observation {trap_tagger_event_trace.object_id} to '{trap_tagger_event_trace.destination.base_url}'"
    assert activity_log.details == event_data


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


def test_process_observation_delivered_event_after_retry_with_single_destination(
        trap_tagger_event_trace, trap_tagger_observation_delivery_failed_event, trap_tagger_observation_delivered_event
):
    # Test the case when an observation fails to get delivered the first time
    # and succeeds on a second try.
    process_event(trap_tagger_observation_delivery_failed_event)
    trap_tagger_event_trace.refresh_from_db()
    assert trap_tagger_event_trace.has_error
    assert trap_tagger_event_trace.error == "Delivery Failed at the Dispatcher."
    # Check that the event was recorded in the activity log
    event_data = json.loads(trap_tagger_observation_delivery_failed_event.data)["payload"]
    event_data["source_external_id"] = trap_tagger_event_trace.source.external_id
    activity_log = ActivityLog.objects.filter(integration_id=event_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.ERROR
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_delivery_failed"
    assert activity_log.title == f"Error Delivering observation {trap_tagger_event_trace.object_id} to '{trap_tagger_event_trace.destination.base_url}'"
    assert activity_log.details == event_data

    # Process the second event. The observation was delivered with success now
    process_event(trap_tagger_observation_delivered_event)
    event_data = json.loads(trap_tagger_observation_delivered_event.data)["payload"]
    trap_tagger_event_trace.refresh_from_db()
    event_data["source_external_id"] = trap_tagger_event_trace.source.external_id
    assert not trap_tagger_event_trace.has_error
    assert not trap_tagger_event_trace.error
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
    assert activity_log.title == f"Observation Delivered to '{trap_tagger_event_trace.destination.base_url}'"
    assert activity_log.details == event_data


def test_process_observation_delivered_event_after_retry_with_two_destinations(
        trap_tagger_event_trace,
        trap_tagger_observation_delivery_failed_event,
        trap_tagger_observation_delivery_failed_event_two,
        trap_tagger_observation_delivered_event,
        trap_tagger_observation_delivered_event_two
):
    # Test the case when an observation fails to get delivered the first time to two destinations
    # and succeeds on a second try for both destinations
    process_event(trap_tagger_observation_delivery_failed_event)
    trap_tagger_event_trace.refresh_from_db()
    assert trap_tagger_event_trace.has_error
    assert trap_tagger_event_trace.error == "Delivery Failed at the Dispatcher."
    process_event(trap_tagger_observation_delivery_failed_event_two)
    event_2_data = json.loads(trap_tagger_observation_delivered_event_two.data)["payload"]
    trap_tagger_event_trace_2 = GundiTrace.objects.get(
        object_id=trap_tagger_event_trace.object_id,
        destination__id=str(event_2_data["destination_id"])
    )
    assert trap_tagger_event_trace_2.has_error
    assert trap_tagger_event_trace_2.error == "Delivery Failed at the Dispatcher."

    process_event(trap_tagger_observation_delivered_event)
    event_data = json.loads(trap_tagger_observation_delivered_event.data)["payload"]
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
    assert activity_log.title == f"Observation {trap_tagger_event_update_trace.object_id} updated in '{trap_tagger_event_update_trace.destination.base_url}'"
    assert activity_log.details == event_data


def test_process_observation_update_failed_event(
        trap_tagger_event_update_trace, trap_tagger_observation_update_failed_event
):
    # Test the case when an observation is updated in a destination successfully
    process_event(trap_tagger_observation_update_failed_event)
    event_data = json.loads(trap_tagger_observation_update_failed_event.data)["payload"]
    event_data["source_external_id"] = trap_tagger_event_update_trace.source.external_id
    trap_tagger_event_update_trace.refresh_from_db()
    assert trap_tagger_event_update_trace.last_update_delivered_at is None
    assert trap_tagger_event_update_trace.has_error
    assert trap_tagger_event_update_trace.error == "Update Failed at the Dispatcher."
    # Check that the error was recorded in the activity logs
    activity_log = ActivityLog.objects.filter(integration_id=event_data["data_provider_id"]).first()
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.EVENT
    assert activity_log.log_level == ActivityLog.LogLevels.ERROR
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.value == "observation_update_failed"
    assert activity_log.title == f"Error Updating observation {trap_tagger_event_update_trace.object_id} in '{trap_tagger_event_update_trace.destination.base_url}'"
    assert activity_log.details == event_data
